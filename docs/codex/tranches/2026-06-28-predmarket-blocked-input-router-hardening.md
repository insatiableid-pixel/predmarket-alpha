# 2026-06-28 Predmarket Blocked-Input Router Hardening

## Scope

Repository: `/home/mrwatson/projects/predmarket-alpha`

Directive: `NEXT_DIRECTIVE_2026-06-28_PREDMARKET_BLOCKED_INPUT_ROUTER_HARDENING.md`

## Result

Predmarket's Type 2 reference tools are still installed and safe, but the macro router now distinguishes tool readiness from missing operator input.

The missing mapped sportsbook reference is now a blocked macro gate:

- Gate: `mapped_sportsbook_reference_available`
- Status: `blocked`
- Evidence status: `kalshi_type2_reference_preflight_blocked_missing_sportsbook_reference`
- Blocker count: non-zero
- Scheduling priority: parked behind actionable repos

## Plain English

Before this tranche, predmarket said: "the preflight tool exists, so I am mostly okay."

Now it says: "the preflight tool exists, but the required sportsbook reference file is missing, so stop here and route to another repo."

## Guardrails

- No provider/API calls.
- No paid calls.
- No live Kalshi actions.
- No account/order/execution paths.
- No database writes.
- No sportsbook reference was invented or synthesized.

## Verification

- `make type2-reference-preflight`: still writes a safe blocked report with no sportsbook reference.
- Focused pytest for router, reference intake, and paper matcher: 20 passed.
- Focused ruff checks: clean.
- `make macro-status`: predmarket has one blocked gate and priority `-3`.
- `make macro-route`: recommends `atp-oracle`.

## Next Blocker

Predmarket remains parked until a local sportsbook reference JSON exists with exact `kalshi_ticker` mappings.
