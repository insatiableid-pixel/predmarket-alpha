# 2026-07-01 Kalshi Contract EV Ledger

## What Changed

- Added `scripts/kalshi_contract_ev_ledger.py`, a command-center ledger that turns every active macro repo into either contract-level Kalshi EV rows or an explicit blocked feed.
- Added `docs/codex/macro/kalshi-contract-ev-ledger.schema.json`.
- Added `make kalshi-ev-ledger`, which writes:
  - `docs/codex/macro/kalshi-contract-ev-ledger-latest/kalshi-contract-ev-ledger.json`
  - `docs/codex/macro/kalshi-contract-ev-ledger-latest/kalshi-contract-ev-ledger.md`
  - `docs/codex/macro/kalshi-contract-ev-ledger-latest/kalshi-contract-ev-ledger.csv`
  - `docs/codex/macro/latest-kalshi-contract-ev-ledger.json`
  - `docs/codex/macro/latest-kalshi-contract-ev-ledger.md`

## Current Ledger Result

- Status: `kalshi_ev_ledger_candidates_present_but_not_usable`
- Repo feeds: 5
- Rows: 316
- Usable rows: 0
- Calibrated positive-margin rows: 0
- Verified official resolution-rule rows: 316
- Missing calibrated-probability rows: 316
- Predmarket rows: 52, all blocked
- MLB rows: 264, all blocked
- ATP: blocked/read-only because another worker is active there
- NBA and NFL: blocked until they emit Kalshi contract mappings with executable costs and calibrated probabilities

## Why Rows Are Blocked

The ledger calculates contract math, but refuses to call anything usable unless the gates pass. Current blockers are:

- probability source is a sportsbook/reference probability, not a calibrated contract probability;
- timing, mapping, or review gates are not clean enough;
- some repos do not yet map their model outputs to concrete Kalshi tickers, sides, payout, and resolution rules.

This is intentional. Reference probabilities are preserved as reference fields, but margin and EV remain blank until a calibrated contract probability exists and the contract-specific gates clear.

## Execution-Hurdle Correction

The ledger treats the best captured execution cost basis as the EV hurdle. The hierarchy is:

1. explicit all-in execution cost, if present;
2. fee-inclusive payout multiplier, if present;
3. gross ticket/order payout multiplier plus explicit or official fee estimate and slippage costs, if present;
4. executable contract price plus explicit or official fee estimate and slippage costs as fallback.

- `contract_price_break_even_probability = executable_price`
- `displayed_price_break_even_probability = display_price`
- `all_in_break_even_probability = explicit all-in cost, else 1 / fee-inclusive payout multiple, else 1 / gross payout multiple + explicit/official fee estimate + slippage, else executable_price + explicit/official fee estimate + slippage`
- `break_even_probability = all_in_break_even_probability`
- `payout_implied_break_even_probability = 1 / kalshi_payout_multiple` when a ticket/order payout is captured
- `all_in_cost` follows the same execution-cost hierarchy
- `effective_hold_probability = all_in_break_even_probability - display_price`
- `margin_probability = calibrated_probability - all_in_break_even_probability`

Example: if the list view shows `0.71` but the buy ticket says `1.34x`, the gross fill hurdle is `1 / 1.34 = 0.7463`. A calibrated probability of `0.74` beats the visible `0.71` but does not beat the gross ticket hurdle, so the row is not usable. Kalshi docs separately define trading fees on matched orders, so the ledger now adds an explicit fee if supplied, otherwise the official fee estimate, unless the source explicitly marks the multiplier as fee-inclusive.

## Official Fee Normalizer

`predmarket.kalshi_execution_cost` centralizes the command-center cost math:

- general taker fee: `ceil_centicent(0.07 * C * P * (1-P))`;
- maker fee: `ceil_centicent(0.0175 * C * P * (1-P))`;
- INX/NASDAQ100 taker fee: `ceil_centicent(0.035 * C * P * (1-P))`;
- `P` is gross contract price in dollars, `C` is contract count, and the default ledger view normalizes one contract.

The ledger now emits `gross_execution_cost`, `fee_estimate`, `fee_source`, `fee_rate`, `fee_mode`, and `cost_quality` for every row.

## Resolution-Rule Gate

The ledger row contract now includes:

- `resolution_rule`
- `resolution_rule_source`
- `resolution_rule_status`

The first version inferred the rule from local contract/ticker/evidence fields. The current version now builds a local official-terms index from Kalshi snapshots such as `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_latest.json`, using exact ticker matches only. When `rules_primary`/`rules_secondary` are present, the row is upgraded to `verified_official_terms` and records:

- `resolution_rule_source_artifact`
- `resolution_rule_source_sha256`

Current Predmarket and MLB rows are 316/316 verified against the local Kalshi snapshot. No raw payload is copied into the repo; the ledger records the outside-repo artifact path and hash as evidence. A row cannot become usable until `resolution_rule_status=verified_official_terms`, and it still needs clean timing/mapping plus a calibrated contract probability.

## Blocker Summary Gate

The ledger now also emits a machine-readable blocker summary:

- `missing_calibrated_probability_row_count`
- `blocked_row_reason_counts`
- `top_blocked_row_reasons`

Current top blocker: `calibrated contract probability is missing` on 316/316 rows. This is deliberately separate from `reference_probability`, because sportsbook no-vig/reference probabilities are not treated as calibrated model probabilities.

## EV Readiness Matrix

Each `repo_feed` now emits `ev_readiness`:

- `contract_mapping_status`
- `official_terms_status`
- `execution_cost_status`
- `calibrated_probability_status`
- `row_gate_status`
- `exact_next_input`
- `next_local_command`

Current interpretation:

- Predmarket and MLB have exact Kalshi contract rows, verified official terms, and fee-aware costs, but no calibrated contract probabilities.
- NFL has calibrated model probabilities in its fair-line packet, but they are not mapped to exact Kalshi contracts with quotes and official terms.
- ATP and NBA remain blocked by their named validation/signal gaps plus missing Kalshi contract mapping.

## Calibrated-Probability Overlay Contract

The ledger can now ingest safe local probability overlays from:

`/home/mrwatson/manual_drops/kalshi_ev_probabilities/`

The manual-drop contract lives at:

`docs/codex/manual-drops/kalshi-ev-calibrated-probability-contract.md`

Each row must be keyed by exact `contract_ticker` and `side`, include a probability in `[0, 1]`, and declare a calibration status. The ledger records `calibration_status`, `calibrated_probability_source_artifact`, and `calibrated_probability_source_sha256` on every row that uses an overlay. Current overlay row count is 0.

## Contract-Mapping Overlay Contract

The ledger can now ingest safe local contract-mapping overlays from:

`/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/`

The manual-drop contract lives at:

`docs/codex/manual-drops/kalshi-ev-contract-mapping-contract.md`

This is the zero-row repo bridge. A repo such as NFL can produce EV rows once a local mapping supplies exact `source_repo_id`, `contract_ticker`, `side`, verified official terms, timing status, and executable quote. A synthetic test proves that a verified mapping plus a validated probability overlay can produce a usable EV row; current real contract-mapping overlay row count is 0.

## Overlay Preflight

`make kalshi-ev-overlay-preflight` validates the two overlay chutes before the ledger depends on them.

It writes:

- `docs/codex/macro/kalshi-ev-overlay-preflight-latest/kalshi-ev-overlay-preflight.json`
- `docs/codex/macro/kalshi-ev-overlay-preflight-latest/kalshi-ev-overlay-preflight.md`
- `docs/codex/macro/latest-kalshi-ev-overlay-preflight.json`
- `docs/codex/macro/latest-kalshi-ev-overlay-preflight.md`

Current status is `overlay_preflight_blocked_missing_or_unjoined_inputs`: 0 mapping files, 0 probability files, 0 exact joins, and 0 usable overlay EV rows. This is correct until a real mapping/probability pair is dropped outside the repo.

## Calibration Work Order

`make kalshi-ev-calibration-work-order` turns the current blocker into an exact assignment queue. It reads the latest EV ledger, excludes rows that already have calibrated probabilities, missing exact ticker/side keys, unverified terms, missing all-in break-even costs, or temporal-mismatch downgrades, then writes:

- `docs/codex/macro/kalshi-ev-calibration-work-order-latest/kalshi-ev-calibration-work-order.json`
- `docs/codex/macro/kalshi-ev-calibration-work-order-latest/kalshi-ev-calibration-work-order.md`
- `docs/codex/macro/kalshi-ev-calibration-work-order-latest/kalshi-ev-calibrated-probability-template.json`
- `docs/codex/macro/latest-kalshi-ev-calibration-work-order.json`
- `docs/codex/macro/latest-kalshi-ev-calibration-work-order.md`
- `docs/codex/macro/latest-kalshi-ev-calibrated-probability-template.json`

Latest status is `calibration_work_order_ready_source_gated`: 316 ledger rows, 312 eligible non-temporal-mismatch candidates with verified official terms and all-in break-even costs, 25 selected rows, 0 direct pass-ready candidates, and 0 usable ledger rows. The generated template is not evidence because probabilities are null. More importantly, these rows still have non-probability source gates, so probabilities alone will not create usable EV rows.

## Contract Mapping Work Order

`make kalshi-ev-contract-mapping-work-order` bridges the more useful lane: NFL has calibrated model probabilities, but no exact Kalshi contract mapping. It reads the local NFL fair-line review and validation artifacts, then writes:

- `docs/codex/macro/kalshi-ev-contract-mapping-work-order-latest/kalshi-ev-contract-mapping-work-order.json`
- `docs/codex/macro/kalshi-ev-contract-mapping-work-order-latest/kalshi-ev-contract-mapping-work-order.md`
- `docs/codex/macro/kalshi-ev-contract-mapping-work-order-latest/kalshi-ev-contract-mapping-template.json`
- `docs/codex/macro/kalshi-ev-contract-mapping-work-order-latest/kalshi-ev-contract-mapped-probability-template.json`
- `docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.json`
- `docs/codex/macro/latest-kalshi-ev-contract-mapping-work-order.md`
- `docs/codex/macro/latest-kalshi-ev-contract-mapping-template.json`
- `docs/codex/macro/latest-kalshi-ev-contract-mapped-probability-template.json`

Latest status is `contract_mapping_work_order_ready`: 16 NFL model rows, 32 selected contract sides, and 2 validation artifacts. The templates are marked `template_only=true` and use TODO statuses, so they cannot become evidence accidentally. The missing facts are exact Kalshi ticker, official terms, clean timing status, and executable cost.

## Router And Scout Integration

`make macro-route` now treats the EV ledger and mapping work orders as the command-center truth surface when EV artifacts exist. Current route:

- recommended repo: `predmarket-alpha`
- status: `kalshi_ev_contract_mapping_work_order_ready`
- priority: `21`
- all lanes parked: `false`
- next tranche: take one selected NFL contract-mapping work-order row, supply exact Kalshi ticker, official terms, clean timing status, and executable cost from local evidence, write matching safe mapping/probability overlays outside the repo, then rerun overlay preflight and the EV ledger

`make macro-unlock-scout` now includes a `kalshi_ev` section with ledger, overlay-preflight, calibration, and contract-mapping work-order summaries. The current exact missing input is exact Kalshi mapping facts plus matching safe overlays under `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/` and `/home/mrwatson/manual_drops/kalshi_ev_probabilities/`.

## Cost-Basis Hardening

Follow-up hardening made the row gates enforce the correction:

- `71%` may be a displayed contract price, but it is rejected as a payout multiple.
- `134%` or `1.34x` may be parsed as a payout multiple and maps to a `0.7463` gross execution break-even when captured from the ticket/order context.
- A row with model probability above visible price can still be blocked if it does not clear the captured ticket payout hurdle.
- A row with gross payout multiple gets the official fee estimate by default unless a more explicit fee/all-in cost field is present.
- A row with no execution cost basis is blocked.
- Rows now expose `contract_price_break_even_probability`, `displayed_price_break_even_probability`, `all_in_break_even_probability`, `payout_implied_break_even_probability`, `cost_basis_source`, and `source_gate_status`.

## Verification

- `TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest -q tests/test_kalshi_contract_ev_ledger.py`
  - 17 passed
- `python -m json.tool docs/codex/macro/kalshi-contract-ev-ledger.schema.json >/dev/null && TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest -q tests/test_kalshi_execution_cost.py tests/test_kalshi_contract_ev_ledger.py tests/test_codex_macro_router.py tests/test_codex_macro_unlock_scout.py`
  - 74 passed
- `.venv/bin/ruff check predmarket/kalshi_execution_cost.py tests/test_kalshi_execution_cost.py scripts/kalshi_contract_ev_ledger.py tests/test_kalshi_contract_ev_ledger.py`
  - all checks passed
- `make kalshi-ev-ledger`
  - wrote latest JSON, Markdown, and CSV outputs
- `make macro-route`
  - all lanes parked; recommended repo remains `predmarket-alpha`
- `make macro-unlock-scout`
  - all lanes still require named external evidence
- `make macro-status`
  - `research_only=true`, `execution_enabled=false`

## Next Useful Work

The highest-leverage follow-up is to make one repo produce a truly calibrated Kalshi contract probability for a concrete ticker, side, executable cost, and resolution rule. NFL and NBA need contract mapping first. Predmarket and MLB already have contract rows, but they need calibrated probability before any row can be usable.
