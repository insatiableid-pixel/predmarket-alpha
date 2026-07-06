# ATP Donor Evidence Gate + Preflight

Date: 2026-07-03

## Objective

Move Wimbledon/ATP from discovery-only into a strict evidence lane without promoting donor probabilities, EV, paper sizing, live orders, or discretionary picks.

## Changes

- Added `scripts/kalshi_atp_proxy_evidence_gate.py`.
- Added `make kalshi-atp-proxy-evidence-gate`.
- Chained `kalshi-atp-proxy-observation-watch-once` through the evidence gate after the ATP observation loop.
- Registered ATP donor evidence artifacts in `predmarket/source_inventory.py`:
  - forward-OOS report
  - forward-OOS liquidity
  - bettable-line gate
  - forward-OOS price observations
  - Kalshi match snapshot
- Extended `predmarket/external_artifact_wrappers.py` so ATP `market_ticker` rows and `observations` / `latest_observations` payloads wrap as safe YES-side market evidence rows.
- Added focused tests for the ATP evidence gate and ATP-shaped donor preflight rows.

## Latest Artifacts

- `docs/codex/macro/latest-kalshi-atp-proxy-evidence-gate.json`
- `docs/codex/macro/latest-source-repo-inventory.json`
- `docs/codex/macro/latest-external-artifact-preflight.json`

Latest ATP evidence status:

- `atp_proxy_evidence_gate_blocked_waiting_settlement_labels`
- 24 ATP observation rows
- 0/10 settled predmarket ATP labels
- 2/10 forward-OOS resolved for probe
- 2/25 forward-OOS resolved for first stake
- 6/25 executable-liquidity candidates
- bettable-line gate blocked

Latest external preflight:

- 16 donor artifacts
- 15 safe
- 974 safe rows
- all ATP donor artifacts pass strict preflight
- the only blocked donor artifact is the optional missing MLB manual model drop

## Guardrails

- ATP donor outputs are evidence inputs only.
- No ATP donor row becomes tradable merely because it passes preflight.
- The evidence gate emits no probabilities, EV, sizing, stake, account, order, or execution output.
- Promotion remains blocked until settled labels plus forward-OOS, liquidity, bettable-line, falsification, replay, capacity, correlation, and decay gates pass.

## Verification

- `ruff check` on touched Python files: pass.
- `make lint-baseline-check`: pass (`lint 1409/1422`, `format 90/94`).
- `make test-unit`: 655 passed / 14 deselected.
- `make test-integration`: 14 passed.
- `tests/test_kalshi_atp_proxy_evidence_gate.py`: 4 passed.
- Focused ATP/paper/live recheck after formatting: 26 passed.
- Refreshed artifact chain: ATP evidence gate, source inventory, external preflight, paper decisions, EV ledger, signal-factory status, and live preflight.

## Next

Wait until `2026-07-04T06:00:00Z` or later, then run `make kalshi-atp-proxy-observation-watch-once` to probe exact public Kalshi settlements. If labels appear, route ATP through falsification/replay before any paper or live promotion.
