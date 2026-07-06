# Passive-Liquidity Paper Fill Falsification

Date: 2026-07-05

## Purpose

Continue implementing Claude's sports advice by turning passive-liquidity paper fill/timeout evidence into an explicit falsification gate.

The previous tranche started the stateful paper maker-intent clock. That was necessary but not sufficient: passive liquidity still needed a separate acceptance ledger so timeout/fill labels could be tested before any paper promotion. This tranche adds that ledger and preserves the key boundary: public-snapshot paper touches are not real Kalshi exchange fills.

## Landing

- Added `scripts/kalshi_passive_liquidity_paper_fill_falsification.py`.
- Added `make kalshi-passive-liquidity-paper-fill-falsification`.
- Wired the target into `make kalshi-sports-nondirectional-evidence-watch-once` after the paper-fill loop.
- Added `latest-kalshi-passive-liquidity-paper-fill-falsification.{json,md,csv}` and canonical latest pointers under `docs/codex/macro/`.
- Updated `scripts/kalshi_sports_evidence_cycle_report.py` so the sports cycle treats passive paper-fill falsification as the 26th safe artifact.
- Added focused tests in `tests/test_kalshi_passive_liquidity_paper_fill_falsification.py`.

## Method

- Join persisted paper maker intents to later public-snapshot labels by `paper_intent_id`.
- Join entry/touch snapshots to the sports microstructure observation archive by snapshot id.
- Treat `paper_filled_from_later_public_touch` as a paper fill and `paper_expired_unfilled_no_public_touch` as a timeout.
- Evaluate three pre-registered buckets: all maker intents, YES maker intents, and NO maker intents.
- Use chronological OOS split, minimum independent labels, minimum OOS labels, minimum OOS fills, and Benjamini-Hochberg FDR.
- Score only filled paper trials for maker fill net EV after adverse selection.

## Guardrails

- `research_only=true`.
- `execution_enabled=false`.
- `market_execution=false`.
- `account_or_order_paths=false`.
- `staking_or_sizing_guidance=false`.
- `usable=false` for the artifact and all candidate rows.
- `real_exchange_fill_label_count=0`.
- No calibrated probability, EV ledger promotion, paper stake, live order, account call, or order path is emitted.
- Timeout-only evidence blocks the gate instead of manufacturing a candidate.

## Real Run

`make kalshi-passive-liquidity-paper-fill-falsification` exits 0.

Current artifact:

- Status: `passive_liquidity_paper_fill_falsification_blocked_no_paper_fills`
- Paper intents: `462`
- Paper fill labels: `226`
- Valid paper fill labels: `226`
- Paper fills: `0`
- Paper timeouts: `226`
- Real exchange fill labels: `0`
- Tested hypotheses: `0`
- FDR survivors: `0`
- Research candidates: `0`

`make kalshi-sports-evidence-cycle-report` exits 0.

Latest sports cycle:

- Status: `sports_evidence_cycle_ready_with_label_progress`
- Safe artifacts: `26/26`
- Passive paper-fill falsification: `passive_liquidity_paper_fill_falsification_blocked_no_paper_fills`
- Paper-usable near-resolution flow rows: `4`
- Paper stake: `$33.659219`
- Paper cap breaches: `0`
- Live eligible rows: `0`

## Verification

- `python -m pytest -s -q tests/test_kalshi_passive_liquidity_paper_fill_falsification.py tests/test_kalshi_sports_evidence_cycle_report.py` -> `7 passed`
- `python -m ruff check` on touched script/test files -> clean
- `python -m ruff format --check` on touched script/test files -> clean
- `make test-unit` -> `1301 passed / 15 deselected`
- `make test-integration` -> `14 passed`
- `make lint-baseline-check` -> exits 0 (`lint 100/1422`, `format 8/94`)
- `make quality` -> exits 0 with existing advisory Ruff/deptry backlog
- `git diff --check` -> only existing line-ending warnings

## Claude Implementation Estimate

After this tranche, the Claude attachment is roughly `82%` implemented.

Implemented:

- Near-resolution informed-flow candidate generation, falsification, replay, terms capture, EV ledger promotion, paper sizing, and live block.
- ATP settlement-window instrumentation.
- World Cup/soccer strict consensus coverage and proxy evidence loop.
- Sports sharp no-vig consensus doctrine, preflight, observation archive, provider audit, and falsification ledger.
- MLB/ATP/NFL/soccer strict consensus wrappers.
- Always-on consensus collector target.
- Passive-liquidity paper intent/label loop.
- Passive-liquidity paper-fill falsification gate.
- Guardrails against loosening labels, bypassing FDR, or promoting donor/projection models directly.

Still incomplete:

- Consensus lane needs enough exact settlement labels and OOS labels to test real survivors.
- NBA strict consensus is still missing.
- Soccer needs Asian-sharp enrichment before provider coverage is mature.
- Event-velocity ETA reporting per family is not yet a first-class artifact.
- World Cup outcome-level independence diagnostics for totals/BTTS are not yet first-class.
- Passive liquidity has no actual paper fills yet, so its FDR gate correctly has no tested hypotheses.
- Paper P&L, calibration drift, and decay retirement need repeated post-close updates.
- Live remains correctly blocked until paper evidence and live-risk gates justify an explicit execution tranche.
