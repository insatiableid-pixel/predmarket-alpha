# Claude Advice Compliance Audit

Date: 2026-07-06

## Objective

Make the active goal, "implement 100% of Claude's advice," auditable against current
machine evidence instead of relying on narrative summaries.

## Landing

- Added `scripts/kalshi_claude_advice_audit.py`.
- Added `make kalshi-claude-advice-audit`.
- Added focused tests at `tests/test_kalshi_claude_advice_audit.py`.
- Generated:
  - `docs/codex/macro/latest-kalshi-claude-advice-audit.json`
  - `docs/codex/macro/latest-kalshi-claude-advice-audit.md`
  - `docs/codex/macro/latest-kalshi-claude-advice-audit.csv`

## Requirements Audited

1. Near-resolution informed-flow candidate generation.
2. Informed-flow full gate chain through replay, EV ledger, paper, capacity, correlation, and decay.
3. Passive-liquidity real paper-fill label accumulation.
4. Passive-liquidity real-fill FDR gate.
5. ATP forward-OOS settlement clock.
6. World Cup outcome-family independence with portfolio clustering by match.
7. Prior-only donor guardrail.
8. Calendar/event-velocity forecast.
9. Avoid live hardening while there are zero live-eligible edges.
10. No threshold relaxation.

## Latest Real Audit

- Status: `claude_advice_audit_ready_with_open_clock_or_statistical_items`.
- Requirements: `10`.
- Satisfied: `8`.
- Clock-bound: `2`.
- Warnings: `0`.
- Unsafe artifacts: `0`.
- Missing artifacts: `0`.

Open clock rows:

- `CLAUDE-008`: event velocity next probe is `sports_consensus_rule_bucket_accumulation`
  at `2026-07-06T03:00:00Z`.
- `CLAUDE-005`: ATP forward-OOS is `2/10`, next probe `2026-07-06T06:00:00Z`.

Notably, passive liquidity with `0` FDR survivors is treated as a satisfied statistical
rejection, not an implementation blocker: real paper-fill labels exist and the gate tested
three hypotheses.

## Guardrails

- Research-only audit.
- No probabilities, EV, paper sizing, live eligibility, or order paths changed.
- No labels inferred from sportsbooks.
- No thresholds lowered.
- Donor priors still get zero label, paper, and live credit.

## Verification

- `TMPDIR=/home/mrwatson/projects/predmarket-alpha/.tmp PYTHONPATH=. .venv/bin/pytest tests/test_kalshi_claude_advice_audit.py -v --tb=short`
  - `3 passed`
- `.venv/bin/ruff check scripts/kalshi_claude_advice_audit.py tests/test_kalshi_claude_advice_audit.py`
  - `All checks passed`
- `make kalshi-claude-advice-audit`
  - exits `0`
- `make lint-baseline-check`
  - exits `0`
- `make quality`
  - exits `0` with the existing advisory Ruff/deptry backlog

## Next Mechanical Action

At or after `2026-07-06T03:00:00Z`, run:

```bash
make kalshi-sports-paper-burn-in-cycle KALSHI_SPORTS_PAPER_BURN_IN_FETCH=1
```

At or after `2026-07-06T06:00:00Z`, rerun ATP exact settlement probing through the sports burn-in
cycle and audit again.
