# 2026-06-27 Predmarket Type 2 Paper Matcher Readiness

## Scope

Repository: `/home/mrwatson/projects/predmarket-alpha`

Directive: `NEXT_DIRECTIVE_2026-06-27_PREDMARKET_TYPE2_PAPER_MATCHER_READINESS.md`

## Result

Predmarket now has a local, paper-only Type 2 matcher:

- Module: `predmarket/type2_paper_matcher.py`
- Tests: `tests/test_type2_paper_matcher.py`
- Make target: `make type2-paper-matcher`
- Latest report: `docs/codex/artifacts/type2-paper-matcher-latest/type2-paper-matcher-latest.json`

The default run is intentionally blocked with `blocked_missing_sportsbook_reference` because no mapped local sportsbook reference JSON was supplied. This is a good blocked state: it prevents fuzzy matching or invented reference prices.

## Guardrails

- No provider/API calls.
- No account/order/execution paths.
- No database writes.
- No raw provider payload copied into the repo.
- `REVIEW_ONLY_PASS` remains manual research review only.

## Verification

- Kalshi-focused suite: 53 passed.
- Type 2 matcher tests: 7 passed.
- Router tests: 4 passed.
- Ruff focused checks: clean.
- `make type2-paper-matcher`: wrote blocked report safely.
- `make macro-status`: status `kalshi_type2_matcher_blocked_missing_sportsbook_reference`.

## Next Blocker

Predmarket Type 2 work needs a local sportsbook reference JSON with explicit `kalshi_ticker` mappings. Until that exists, the macro router should prefer another repo.
