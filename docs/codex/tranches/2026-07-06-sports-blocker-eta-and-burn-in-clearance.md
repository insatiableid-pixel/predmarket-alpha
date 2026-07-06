# Sports Blocker ETA And Burn-In Clearance

Date: 2026-07-06

## Objective

Clear the sports blocker surfaces that were software/reporting ambiguities, then run the due paper burn-in cycle after the next settlement clock without lowering statistical gates or promoting any unproven signal.

## What Changed

- Added a `sports_consensus_rule_bucket_accumulation` row to `scripts/kalshi_sports_event_velocity_eta.py`.
- Surfaced that nearest no-vig consensus rule/bucket ETA in `scripts/kalshi_sports_evidence_cycle_report.py`.
- Updated the sports evidence report so the legacy passive-liquidity proxy-only blocker is ignored once paper-fill labels exist and paper-fill falsification is ready.
- Added `next_expected_expiration_utc` to `scripts/kalshi_atp_proxy_evidence_gate.py` and threaded that timestamp into the ATP ETA row, while keeping the old ATP forward-OOS gate blocked.
- Ran the sports paper burn-in cycle after the `2026-07-06T02:20:00Z` close boundary with public settlement fetch enabled.

## Current Evidence State

- Consensus falsification remains `sports_consensus_falsification_blocked_no_testable_hypotheses`.
- Nearest deficient consensus hypothesis: `sports_consensus_price_bucket_bias_bucket_0.50_0.70`.
- Nearest hypothesis OOS state: `5/10`, deficit `5`.
- Consensus accumulation opportunities: `270` rows across `103` distinct pending contracts.
- Nearest-hypothesis opportunities: `33`.
- Next consensus rule/bucket probe: `2026-07-06T03:00:00Z`.
- Passive maker state: `passive_liquidity_paper_fill_falsification_ready_no_research_candidates`, `1752` paper fill/timeout labels, `0` FDR survivors.
- ATP forward-OOS state: `2/10`, next expected expiration/probe `2026-07-06T06:00:00Z`; still blocked.
- Paper state after burn-in: `10` usable unresolved rows, `$220.846241` total paper stake, next paper close `2026-07-06T03:00:00Z`.
- Live state: `kalshi_live_blocked`, `470` decisions, `0` eligible, `$0` live stake.

## Guardrails

- No sportsbook labels were used as settlement labels.
- No FDR/OOS threshold was lowered.
- No EV, paper, or live promotion changed as a result of these control-plane fixes.
- Live execution remains disabled and unarmed.

## Verification

- Focused ATP/ETA/evidence tests: `20 passed`.
- Broader focused sports tests: `34 passed`.
- `make test-unit`: `1359 passed / 15 deselected`.
- `make test-integration`: `14 passed`.
- `make lint-baseline-check`: `OK lint 98/1422 format 12/94`.
- `make quality`: exits `0` with existing advisory Ruff/deptry backlog.
- Touched-file Ruff: clean.
- Touched-file `git diff --check`: clean.

## Next Action

Run `make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1` at or after `2026-07-06T03:00:00Z`, then inspect whether the consensus rule/bucket OOS count advances from `5/10` and whether any paper rows settle into decay/retirement.
