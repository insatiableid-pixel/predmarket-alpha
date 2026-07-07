# 2026-07-07 Fable Audit Demotion Semantics

## Purpose

Fix the Fable/Claude advice audit so a stricter statistical gate that evaluates
and rejects a signal is not misclassified as missing implementation.

The trigger was the near-resolution informed-flow lane after price-implied-null
hardening: the gate has current testable rows, but correctly emits
`near_resolution_informed_flow_falsification_ready_no_research_candidate`.
That is an honest no-edge result, not a reason to manufacture a candidate.

## Changes

- Updated `scripts/kalshi_claude_advice_audit.py`.
- `CLAUDE-001` is implementation-satisfied when the informed-flow falsification
  surface has testable candidates and either emits a research candidate or
  statistically rejects all candidates under the stricter price-implied null.
- `CLAUDE-002` is implementation-satisfied when the replay/EV/paper chain
  artifacts exist and are wired, even if replay is blocked only because the
  upstream informed-flow gate produced no research candidate.
- Added a regression test proving price-implied-null rejection leaves
  implementation at `10/10` while evidence clocks remain separate.
- Regenerated the missing prior-only donor artifact before re-running the audit.

## Latest Evidence

- Fable audit: `claude_advice_audit_ready_with_open_clock_or_statistical_items`.
- Implementation: `10/10` satisfied, `0` open implementation items.
- Evidence: `8/10` satisfied, open only:
  - `CLAUDE-005` ATP forward-OOS, `8/10`, next probe `2026-07-07T06:00:00Z`.
  - `CLAUDE-008` sports consensus event velocity.
- Sports consensus falsification:
  - `574` joined labels.
  - `54` independent labels.
  - `17` OOS labels.
  - `0` tested hypotheses.
  - `0` FDR survivors.
  - nearest bucket: `sports_consensus_price_bucket_bias_bucket_0.30_0.50`,
    OOS deficit `2`, next probe `2026-07-07T04:45:00Z`.

## Guardrails

- No thresholds lowered.
- No labels inferred.
- No sportsbook-derived settlement labels.
- No EV, paper, or live promotion.
- No account/order/live execution path touched.

## Verification

- `.venv/bin/ruff format scripts/kalshi_claude_advice_audit.py tests/test_kalshi_claude_advice_audit.py`
- `.venv/bin/ruff check scripts/kalshi_claude_advice_audit.py tests/test_kalshi_claude_advice_audit.py`
- `.venv/bin/python -m pytest tests/test_kalshi_claude_advice_audit.py tests/test_kalshi_sports_blocker_clearance_cycle.py -q`
- `make kalshi-claude-advice-audit`
- `make kalshi-sports-blocker-clearance-cycle`

Result: focused tests `8 passed`; Ruff clean; both Make targets exit `0`.
