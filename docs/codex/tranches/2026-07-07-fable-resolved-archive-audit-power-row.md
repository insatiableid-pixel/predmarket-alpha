# Fable Resolved-Archive Audit Power Row

Date: 2026-07-07

## Why

Fable's sports advice calls for a public Kalshi resolved-market archive large enough to power price-bucket/favorite-longshot falsification cells. The backfill target existed, but the Fable machine audit did not explicitly score whether the archive had crossed the 1,000 independent-label power floor.

## What Changed

- Ran `make kalshi-resolved-archive-backfill`.
- Added `CLAUDE-013` to `scripts/kalshi_claude_advice_audit.py`:
  - `resolved_archive_price_bucket_power`
  - satisfied only when the resolved archive has at least `1,000` labels, at least `1,000` distinct contracts, observations, and at least one tested hypothesis
  - a no-survivor FDR result counts as satisfied evidence, not as a reason to invent a new threshold
- Added tests proving:
  - a powered 1,184-label archive satisfies `CLAUDE-013`
  - a 999-label archive remains blocked

## Real Backfill Result

`make kalshi-resolved-archive-backfill` emitted:

- status: `kalshi_resolved_archive_backfill_ready_no_fdr_survivors`
- raw markets: `1,200`
- eligible settled markets: `1,184`
- labels: `1,184`
- distinct contracts: `1,184`
- observations: `3,552`
- candlestick markets: `1,200`
- tested hypotheses: `2`
- FDR survivors: `0`
- max hypothesis OOS labels: `188`
- sport: `baseball_mlb`

Interpretation: this powers the public Kalshi-only price-bucket archive lane and rejects the tested bucket hypotheses at current gates. It does not create a tradable signal.

## Guardrails

- No thresholds changed.
- No post-hoc bucket creation.
- No sportsbook-inferred labels.
- No EV, paper stake, candidate promotion, or live eligibility changed.
- No account, order, or execution path touched.

## Verification

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp /home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m pytest tests/test_kalshi_claude_advice_audit.py tests/test_kalshi_resolved_archive_backfill.py -q
/home/mrwatson/projects/predmarket-alpha/.venv/bin/ruff check scripts/kalshi_claude_advice_audit.py tests/test_kalshi_claude_advice_audit.py scripts/kalshi_resolved_archive_backfill.py tests/test_kalshi_resolved_archive_backfill.py
 /home/mrwatson/projects/predmarket-alpha/.venv/bin/python -m py_compile scripts/kalshi_claude_advice_audit.py scripts/kalshi_resolved_archive_backfill.py
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-resolved-archive-backfill
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-claude-advice-audit
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make lint-baseline-check
```

Results:

- focused tests: `11 passed`
- Ruff: pass
- py-compile: pass
- resolved archive target: exit `0`
- Claude/Fable audit target: exit `0`
- lint baseline: pass (`lint 98/1422`, `format 20/94`)
