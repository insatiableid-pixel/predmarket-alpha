# Fable Historical-Consensus Audit Row

Date: 2026-07-07

## Why

Fable's advice permits historical sharp-consensus divergence backfill only under strict timestamp discipline: the provider snapshot and Kalshi quote must remain within `180s` of the target time. The repo already had feasibility and replay surfaces, but the top-level Claude/Fable audit did not explicitly distinguish "implemented" from "evidence blocked by paid historical access / missing archive."

## What Changed

- Added `CLAUDE-014` to `scripts/kalshi_claude_advice_audit.py`:
  - `historical_sharp_consensus_backfill`
  - implementation is satisfied only when both feasibility and backfill artifacts exist and the skew gate passes
  - evidence is satisfied only when the historical replay reaches valid observations and OOS/FDR-tested hypotheses
  - current missing paid access/archive state is reported as `blocked_external`
- Added tests proving:
  - the current paid-access-unverified / missing-archive state remains evidence-blocked
  - a replay that reaches historical observations and FDR testing becomes satisfied

## Real State

Current artifacts report:

- feasibility: `kalshi_sports_historical_consensus_feasibility_ready_paid_access_unverified`
- expected max skew: `150s`
- skew policy: `180s`
- paid access verified: `false`
- backfill: `kalshi_sports_historical_consensus_backfill_blocked_missing_historical_archive`
- historical consensus rows: `0`
- valid observations: `0`
- tested hypotheses: `0`
- FDR survivors: `0`

Interpretation: the historical route is correctly built and gated, but it cannot produce evidence until a replayable paid historical no-vig consensus archive is supplied.

## Guardrails

- No thresholds changed.
- No provider board rows treated as settlement labels.
- No historical rows inferred without timestamped archive provenance.
- No EV, paper stake, candidate promotion, or live eligibility changed.
- No account, order, or execution path touched.

## Verification

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp /home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m pytest tests/test_kalshi_claude_advice_audit.py tests/test_kalshi_sports_historical_consensus_feasibility.py tests/test_kalshi_sports_historical_consensus_backfill.py -q
/home/mrwatson/projects/predmarket-alpha/.venv/bin/ruff check scripts/kalshi_claude_advice_audit.py tests/test_kalshi_claude_advice_audit.py scripts/kalshi_sports_historical_consensus_feasibility.py scripts/kalshi_sports_historical_consensus_backfill.py tests/test_kalshi_sports_historical_consensus_feasibility.py tests/test_kalshi_sports_historical_consensus_backfill.py
/home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m py_compile scripts/kalshi_claude_advice_audit.py scripts/kalshi_sports_historical_consensus_feasibility.py scripts/kalshi_sports_historical_consensus_backfill.py
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-historical-consensus-feasibility
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-historical-consensus-backfill
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-claude-advice-audit
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make lint-baseline-check
```

Results:

- focused tests: `16 passed`
- Ruff: pass
- py-compile: pass
- historical feasibility target: exit `0`
- historical backfill target: exit `0`
- Claude/Fable audit target: exit `0`
- lint baseline: pass (`lint 98/1422`, `format 20/94`)
