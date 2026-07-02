# 2026-06-28 Predmarket Type 2 Reference Intake Preflight

## Scope

Repository: `/home/mrwatson/projects/predmarket-alpha`

Directive: `NEXT_DIRECTIVE_2026-06-28_PREDMARKET_TYPE2_REFERENCE_INTAKE_PREFLIGHT.md`

## Result

Predmarket now has a local sportsbook reference preflight:

- Module: `predmarket/type2_reference_intake.py`
- Tests: `tests/test_type2_reference_intake.py`
- Make target: `make type2-reference-preflight`
- Manual contract: `docs/codex/manual-drops/predmarket-type2-sportsbook-reference-contract.md`
- Latest report: `docs/codex/artifacts/type2-reference-preflight-latest/type2-reference-preflight-latest.json`

The default run is intentionally blocked with `blocked_missing_sportsbook_reference`. That is the correct state because no mapped local sportsbook reference JSON was supplied.

## Guardrails

- No provider/API calls.
- No paid calls.
- No account/order/execution paths.
- No database writes.
- No raw provider payload copied into the repo.
- No fuzzy matching.
- A ready preflight only permits paper-matcher review.

## Verification

- `make type2-reference-preflight`: wrote blocked report safely.
- Focused pytest: 17 passed.
- Focused ruff checks: clean.
- `make type2-paper-matcher`: wrote blocked report safely.

## Next Blocker

Predmarket still needs a small local sportsbook reference JSON with exact `kalshi_ticker` mappings. The next correct command after that file exists is:

```bash
make type2-reference-preflight TYPE2_SPORTSBOOK_JSON=/path/to/reference.json
```

Only run the matcher against that file if the preflight reports `reference_ready`.
