# 2026-06-28 Macro Parked-State Router Summary

## Scope

Repository: `/home/mrwatson/projects/predmarket-alpha`

Directive: `NEXT_DIRECTIVE_2026-06-28_MACRO_PARKED_STATE_ROUTER_SUMMARY.md`

## Result

The macro router now detects when every active repo is parked or waiting on external evidence.

When all repo priorities are `<= 0`, the router:

- sets `all_lanes_parked=true`;
- recommends `predmarket-alpha` as the command center;
- writes a compact `blocker_summary`;
- preserves the ranked repo list;
- stops before inventing missing evidence or starting another parked tranche.

## Plain English

Before this tranche, once predmarket, ATP, and MLB were parked, the router surfaced NFL again even though NFL governance evidence was already fresh.

Now it says the real thing: no repo has a positive actionable tranche. The right next move is to gather missing inputs or wait for evidence to go stale, not keep coding around absent data.

## Guardrails

- No provider/API calls.
- No paid calls.
- No database writes.
- No market execution.
- No model promotion.
- No score/readiness upgrades.
- No missing sportsbook, Kalshi, user, commercial, or validation evidence was invented.

## Verification

- Focused router tests: 15 passed.
- Focused router ruff: clean.
- `make macro-route`: writes `all_lanes_parked=true` and recommends `predmarket-alpha`.

## Current Unlocks

- Predmarket: mapped sportsbook reference JSON with exact `kalshi_ticker` mappings.
- MLB: same-slate sportsbook and Kalshi pregame drops captured strictly before first pitch.
- ATP: fresh local validation/promotion evidence plus D3/G5/P5 external proof before readiness changes.
- NBA: new source-backed signal or market dataset; residual variants are parked at market parity.
- NFL: no immediate work while governance snapshots remain fresh.
