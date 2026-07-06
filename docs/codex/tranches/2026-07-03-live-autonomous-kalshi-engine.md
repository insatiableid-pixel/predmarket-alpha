# 2026-07-03 Live-Autonomous Kalshi Engine

## Landing

Built the first live-autonomous Kalshi event-contract execution layer on top of
the existing paper-autonomous EV engine.

New library surfaces:

- `predmarket/kalshi_live_client.py`: authenticated Kalshi REST V2 client using
  RSA-PSS headers, `/portfolio/events/orders` create-order V2 payloads, current
  `bid=yes` / `ask=no` direction semantics, current market/account/order methods,
  and deterministic client order IDs.
- `predmarket/kalshi_live_engine.py`: live eligibility boundary,
  restart-safe JSON state store, strict cap math, kill-switch checks, live order
  sizing, one-shot autonomous submit loop, and order reconciliation.
- `predmarket/kalshi_live_artifacts.py`: live preflight/trader/reconcile/risk
  report writers.

New CLI/Make targets:

- `make kalshi-live-preflight`
- `make kalshi-live-demo`
- `make kalshi-live-trader`
- `make kalshi-live-reconcile`
- `make kalshi-live-risk-snapshot`

Config added:

- `kalshi_live.execution_mode`: `disabled | demo | live`, default `disabled`.
- Strict defaults: `$250` max open exposure, `$25` per contract, `$100` per
  family, `$50` per cluster, `$100` daily gross buys, `$50` daily loss, 300s
  no-new-entry buffer, 60s unreconciled-order timeout, 5 orders/run.
- Production live still requires explicit config execution, credentials, and
  both documented production-live arming environment variables.

## Current Status

The engine is operational as an unattended live-autonomous layer, but the latest
local run is correctly blocked because the repo is not armed and no account
snapshot is available in unarmed mode.

Latest artifacts:

- `latest-kalshi-live-preflight`: `kalshi_live_blocked`, 348 decisions, 0 live
  eligible, 12 safe donor artifacts, `$0` stake.
- `latest-kalshi-live-trader`: `kalshi_live_blocked`, 348 decisions, 0 live
  eligible, blocked by disabled config/env arming plus missing account snapshot.
- `latest-kalshi-live-risk-snapshot`: ready, 0 open exposure, no kill switches.
- `latest-kalshi-live-reconcile`: blocked without a valid authenticated client.

No live production order was submitted in this tranche.

## Verification

Passed:

- `PYTHONPATH=. .venv/bin/pytest -s tests/test_kalshi_live_client.py tests/test_kalshi_live_engine.py tests/test_config.py tests/test_kalshi_paper_autonomous_engine.py -q`
- `make test-unit` — 638 passed, 14 deselected.
- `make test-integration` — 14 passed.
- `make kalshi-signal-factory-status`
- `make kalshi-ev-ledger`
- `make kalshi-external-artifact-preflight`
- `make kalshi-live-preflight`
- `make kalshi-live-trader`
- `make kalshi-live-reconcile`
- `make kalshi-live-risk-snapshot`
- `make quality` exits 0 with the repo's advisory backlog output.
- `make tech-debt-check`, `make file-sizes-check`, and `make modularize` pass.

Known verification nuance:

- `make lint-baseline-check` currently fails with `format 100 > 94` because
  six already-present untracked paper/donor-foundation files under
  `predmarket/` are counted by the ratchet. The new live-engine files are
  formatted and do not appear in Ruff's format backlog.
