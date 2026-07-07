# Historical Paid-Access Probe Status

Date: 2026-07-07

## Why

Fable's historical sharp-consensus backfill requirement is only admissible if timestamp skew is within policy and historical provider access is actually available. The feasibility artifact already modeled the skew gate, but a real failed paid endpoint probe still landed under the vague status `kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified`.

That was too soft. Once the repo has run a paid-access probe and received a failure, the blocker should say so explicitly.

## What Changed

- `scripts/kalshi_sports_historical_consensus_feasibility.py` now emits `kalshi_sports_historical_consensus_feasibility_blocked_paid_access_probe` when a paid probe exists but does not verify access.
- `scripts/kalshi_claude_advice_audit.py` now includes `paid_probe=<status>` in `CLAUDE-014` evidence.
- Added tests for:
  - failed paid probe status
  - Fable audit evidence surfacing the paid-probe blocker

## Real State

Real probe:

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-historical-consensus-feasibility KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE=1
```

Result:

- feasibility status: `kalshi_sports_historical_consensus_feasibility_blocked_paid_access_probe`
- skew gate: `true`
- max expected absolute skew: `150.0` seconds
- max allowed skew: `180` seconds
- paid access verified: `false`
- paid probe status: `historical_probe_blocked_http_error`
- sanitized provider response: `401 Unauthorized`

Dependent backfill remains:

- status: `kalshi_sports_historical_consensus_backfill_blocked_missing_historical_archive`
- historical rows: `0`
- valid observations: `0`
- tested hypotheses: `0`
- FDR survivors: `0`

## Guardrails

- No historical provider rows were used as settlement labels.
- No threshold lowering or skew relaxation.
- No probabilities, EV rows, paper stake, or live eligibility changed.
- No account, order, or execution path touched.
- No API key material was printed.

## Verification

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_sports_historical_consensus_feasibility.py tests/test_kalshi_claude_advice_audit.py -q
.venv/bin/ruff check scripts/kalshi_sports_historical_consensus_feasibility.py scripts/kalshi_claude_advice_audit.py tests/test_kalshi_sports_historical_consensus_feasibility.py tests/test_kalshi_claude_advice_audit.py
.venv/bin/python -m py_compile scripts/kalshi_sports_historical_consensus_feasibility.py scripts/kalshi_claude_advice_audit.py
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-historical-consensus-feasibility KALSHI_SPORTS_HISTORICAL_CONSENSUS_PROBE=1
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-historical-consensus-backfill
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-claude-advice-audit
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make lint-baseline-check
```

Results:

- focused tests: `14 passed`
- Ruff: pass
- py-compile: pass
- paid feasibility probe: exit `0`
- historical backfill: exit `0`
- Fable audit: exit `0`
- lint baseline: pass (`lint 98/1422`, `format 20/94`)
