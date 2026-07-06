# Sports Consensus Hypothesis Accumulation Plan

Date: 2026-07-05

## Landing

Cleared the remaining ambiguity in the sports no-vig consensus falsification blocker. The global
label floor is now met, but no pre-registered rule/threshold or price-bucket hypothesis has enough
OOS labels to enter FDR. The falsification artifact now emits a machine-readable
`hypothesis_accumulation_plan` naming every blocked pre-registered cell and its exact independent
and OOS deficits.

Latest state:

- Consensus falsification status: `sports_consensus_falsification_blocked_no_testable_hypotheses`
- Independent labels: `31/30`
- OOS labels: `10/10`
- Tested hypotheses: `0`
- FDR survivors: `0`
- Max hypothesis OOS count: `5/10`
- Hypothesis accumulation rows: `30`
- Nearest OOS deficit: `5`
- Nearest cell: `sports_consensus_price_bucket_bias` / bucket `0.50_0.70`

## Guardrails Preserved

- No thresholds were lowered.
- No post-hoc rules were added.
- The accumulation plan is descriptive only: `research_only=true`, `usable=false`.
- No EV, paper stake, live eligibility, account, order, or execution path is enabled by this artifact.

## Files

- `predmarket/sports_consensus_falsification.py`
- `scripts/kalshi_sports_evidence_cycle_report.py`
- `tests/test_kalshi_sports_consensus_falsification.py`
- `tests/test_kalshi_sports_evidence_cycle_report.py`
- `docs/codex/macro/latest-kalshi-sports-consensus-falsification.json`
- `docs/codex/macro/latest-kalshi-sports-evidence-cycle.json`

## Verification

- Focused tests: `14 passed`
- Touched-file Ruff: clean
- `make kalshi-sports-consensus-falsification`: exits `0`
- `make kalshi-sports-evidence-cycle-report`: exits `0`

Remaining real blockers:

- Soccer remains the only active provider-coverage gap.
- NBA remains deferred because there are no current rows.
- Consensus needs future exact Kalshi settlement labels in the named cells before FDR can test.
- Passive liquidity has paper-fill evidence but no FDR survivor.
- Live remains correctly blocked with `0` eligible rows.
