# Prior-Only Donor Gate

## Purpose

Continue implementing Claude's advice: build a prior-only donor layer for cold-starting thin-data Kalshi families, while preserving the core falsification rule. Donor priors may seed hypothesis generation, but they must never satisfy label counts or become tradable probabilities merely because a donor artifact exists.

## What Landed

- Added `predmarket/prior_only_donor.py`.
- Added `scripts/kalshi_prior_only_donor_gate.py`.
- Added `tests/test_kalshi_prior_only_donor_gate.py`.
- Added `make kalshi-prior-only-donor-gate`.
- Wrote latest macro artifacts:
  - `docs/codex/macro/latest-prior-only-donor-gate.json`
  - `docs/codex/macro/latest-prior-only-donor-gate.md`
  - `docs/codex/macro/latest-prior-only-donor-gate.csv`

The writer only updates root `latest-*` pointers when the output directory is under `docs/codex/macro`, so tmp test outputs cannot clobber real macro landing state.

The gate consumes:

- `docs/codex/macro/latest-external-artifact-preflight.json`
- `docs/codex/macro/latest-signal-formula-registry.json`

It emits donor context rows only with:

- `admission_scope=hypothesis_generation_only`
- `counts_toward_settlement_labels=false`
- `counts_toward_independent_labels=false`
- `counts_toward_oos_labels=false`
- `direct_probability_promotion_allowed=false`
- `expected_value_per_contract=null`
- `paper_stake=0`
- `paper_usable=false`
- `live_eligible=false`
- `live_stake=0`

Rows with label/outcome-like payloads or direct EV/paper/live promotion fields are blocked from prior eligibility.

## Real Refreshed State

- External preflight: `external_artifact_preflight_ready`
- Safe donor artifacts: `15/16`
- Safe donor rows: `974`
- Signal formula registry: `signal_formula_registry_ready`
- Formula count ready for multiple testing: `2`
- Prior-only donor gate: `prior_only_donor_gate_ready`
- Prior context rows: `974`
- Eligible prior context rows: `797`
- Blocked prior context rows: `177`
- Settlement label credit: `0`
- Independent label credit: `0`
- OOS label credit: `0`
- Direct probability promotions: `0`
- EV rows: `0`
- Paper-usable rows: `0`
- Live-eligible rows: `0`

Source row counts:

- `nfl_quant_glm51_greenfield`: `830`
- `atp-oracle`: `78`
- `mlb-platform`: `54`
- `us-statarb-lab`: `8`
- `nba-analytics-platform`: `4`

## Verification

```bash
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest -q tests/test_kalshi_prior_only_donor_gate.py
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff check predmarket/prior_only_donor.py scripts/kalshi_prior_only_donor_gate.py tests/test_kalshi_prior_only_donor_gate.py
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m ruff format --check predmarket/prior_only_donor.py scripts/kalshi_prior_only_donor_gate.py tests/test_kalshi_prior_only_donor_gate.py
TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m py_compile predmarket/prior_only_donor.py scripts/kalshi_prior_only_donor_gate.py
TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-external-artifact-preflight
TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-signal-formula-registry
TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-prior-only-donor-gate
```

Results:

- Focused tests: `4 passed`
- Ruff check: clean
- Ruff format check: clean
- Py compile: clean
- All three Make targets exit `0`
- `make test-unit`: `1322 passed / 15 deselected`
- `make test-integration`: `14 passed`
- `make lint-baseline-check`: `lint 100/1422`, `format 8/94`
- `make quality`: exits `0` with existing advisory Ruff/deptry backlog
- `git diff --check`: exits `0` with only CRLF warnings

## Guardrails

- No donor row is a settlement label.
- No donor row satisfies independent or OOS label counts.
- No donor row writes calibrated probability, EV, paper stake, or live eligibility.
- Generated formulas still must enter the multiple-testing/FDR ledger.
- Live remains blocked unless downstream evidence independently passes.

## Remaining Claude Gaps

- Sports consensus still lacks sufficient exact Kalshi settlement labels for OOS/FDR.
- Soccer strict consensus rows exist, but provider coverage is not mature until an Asian sharp source is legally available and adapted.
- NBA strict adapter exists but has no current NBA Kalshi rows in the offseason state.
- Passive liquidity has started real paper-fill labels, but only `3` paper fills and no FDR survivor.
- Repeated post-close paper P&L and decay updates still need more resolved paper decisions.
