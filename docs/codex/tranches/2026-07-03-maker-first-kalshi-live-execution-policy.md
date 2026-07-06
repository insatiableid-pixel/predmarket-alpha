# Maker-First Kalshi Live Execution Policy

Date: 2026-07-03

## Objective

Implement the market-structure advice that Kalshi taker fees are a real edge
hurdle and that the default live path should rest passive, post-only limit
orders unless measured signal decay justifies crossing the spread.

## Changes

- Added `kalshi_live.execution_strategy`, defaulting to `maker_first`, with
  `maker_first`, `taker_cross`, and `taker_if_decay_justifies` modes.
- Added passive execution controls:
  `kalshi_live.passive_order_ttl_seconds` and
  `kalshi_live.passive_price_improvement`.
- Changed `KalshiTradingClient.create_order()` default payload to current V2
  passive behavior: `time_in_force=good_till_canceled`, `post_only=true`, and
  `self_trade_prevention_type=maker`.
- Kept explicit taker crossing available only when configured:
  `time_in_force=immediate_or_cancel`, `post_only=false`, and
  `self_trade_prevention_type=taker_at_cross`.
- Rejected invalid IOC payloads with `expiration_time`.
- Corrected NO-side V2 payload pricing: live decisions keep outcome-side
  prices, but the adapter submits NO orders as YES-book asks at
  `1 - no_price`, matching Kalshi's order-book convention.
- Added maker/taker fee accounting in live eligibility:
  taker fee estimate, maker fee estimate, and maker fee savings.
- Made `taker_if_decay_justifies` block unless the candidate carries measured
  edge decay fast enough to overcome the maker/taker fee-savings penalty over
  the passive TTL.
- Extended live decisions, intents, submitted-order records, markdown, CSV, and
  preflight summaries with execution strategy, fee mode, modeled limit price,
  time-in-force, post-only, expiration, and fee-savings fields.

## Latest Artifact

`make kalshi-live-preflight` writes the latest disabled/unarmed report:

- Status: `kalshi_live_blocked`
- Execution mode: `disabled`
- Decisions: `388`
- Live eligible: `0`
- Live stake: `$0`
- Maker-first decisions: `388`
- Post-only decisions: `388`

This is the intended default. No live order was submitted.

## Verification

- `.venv/bin/python -m py_compile predmarket/kalshi_live_engine.py predmarket/kalshi_live_client.py predmarket/kalshi_live_artifacts.py predmarket/config.py`
- `.venv/bin/python -m pytest -s tests/test_kalshi_live_client.py tests/test_kalshi_live_engine.py tests/test_kalshi_execution_cost.py -q` -> 19 passed
- `.venv/bin/ruff format ...` and `.venv/bin/ruff check ...` on touched files -> clean
- `make test-unit` -> 666 passed, 14 deselected
- `make test-integration` -> 14 passed
- `make kalshi-live-preflight` -> exits 0, writes blocked maker-first report

## Guardrails

- No thresholds were lowered.
- No market orders were added.
- No manual approval queue was added.
- Production live remains blocked unless explicitly armed by config and env.
