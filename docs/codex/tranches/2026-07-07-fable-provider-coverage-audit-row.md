# Fable Provider-Coverage Audit Row

Date: 2026-07-07

## Why

Fable's sports thesis depends on timestamp-matched sharp no-vig consensus being the model. That requires provider coverage across target sports, not just an observation loop. The repo had `latest-kalshi-sports-consensus-provider-audit.json`, but the top-level Claude/Fable audit did not explicitly score whether all target sports had mature sharp-provider coverage.

## What Changed

- Added `CLAUDE-015` to `scripts/kalshi_claude_advice_audit.py`:
  - `sharp_consensus_provider_coverage`
  - implementation is satisfied when the provider-audit artifact exists with at least four strict consensus providers and four anchor providers
  - evidence is satisfied only when every target sport has strict and mature provider coverage with no actionable or deferred gaps
- Added tests proving:
  - the current per-sport-gap state remains evidence-blocked
  - all-target-sport provider coverage becomes satisfied

## Real State

Current provider audit reports:

- status: `sports_consensus_provider_audit_ready_with_per_sport_gaps`
- target sports: `5`
- strict consensus sports: `4/5`
- mature covered sports: `3/5`
- actionable gaps: `1`
- deferred sports: `1`
- strict consensus providers: `4`
- anchor providers: `4`

Interpretation: the provider-control plane is built, but all-sport sharp consensus coverage is not complete yet. This remains a real evidence/source blocker, not a paper-trading blocker.

## Guardrails

- No weak sportsbook rows promoted as sharp consensus.
- No labels inferred.
- No thresholds changed.
- No EV, paper stake, candidate promotion, or live eligibility changed.
- No account, order, or execution path touched.

## Verification

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp /home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m pytest tests/test_kalshi_claude_advice_audit.py tests/test_kalshi_sports_consensus_provider_policy.py tests/test_kalshi_sports_consensus_sharp_provider_capture.py -q
/home/mrwatson/projects/predmarket-alpha/.venv/bin/ruff check scripts/kalshi_claude_advice_audit.py tests/test_kalshi_claude_advice_audit.py predmarket/sports_consensus_sharp_provider_capture.py scripts/kalshi_sports_consensus_provider_audit.py scripts/kalshi_sports_consensus_sharp_provider_capture.py
/home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m py_compile scripts/kalshi_claude_advice_audit.py scripts/kalshi_sports_consensus_provider_audit.py scripts/kalshi_sports_consensus_sharp_provider_capture.py predmarket/sports_consensus_sharp_provider_capture.py
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-consensus-provider-audit
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-claude-advice-audit
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make lint-baseline-check
```

Results:

- focused tests: `27 passed`
- Ruff: pass
- py-compile: pass
- provider audit target: exit `0`
- Claude/Fable audit target: exit `0`
- lint baseline: pass (`lint 98/1422`, `format 20/94`)
