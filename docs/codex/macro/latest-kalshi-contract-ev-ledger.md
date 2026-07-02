# Kalshi Contract EV Ledger

- Status: `kalshi_ev_ledger_ready_with_usable_contract_edges`
- Research only: `true`
- Rows: `348`
- Usable rows: `12`
- Positive-edge rows: `12`
- Verified official resolution-rule rows: `348`
- Inferred resolution-rule rows: `0`
- Missing calibrated-probability rows: `316`
- Local calibrated-probability overlay rows: `32`
- Local contract-mapping overlay rows: `32`

## Contract Math

- `contract_price_break_even_probability = executable_price`
- `displayed_price_break_even_probability = display_price`
- `all_in_break_even_probability` uses explicit all-in cost first, then fee-inclusive payout multiple, then gross ticket payout plus explicit/official fee estimate, then executable price plus explicit/official fee estimate.
- `break_even_probability` is an alias for `all_in_break_even_probability`
- `payout_implied_break_even_probability = 1 / payout_multiple` when a ticket/order payout is present.
- `all_in_cost` follows the same cost-basis hierarchy as `all_in_break_even_probability`.
- `effective_hold_probability = break_even_probability - display_price`
- `margin_probability = calibrated_probability - break_even_probability`
- `expected_value_per_contract = calibrated_probability * payout_if_correct - all_in_cost`
- `resolution_rule_status = verified_official_terms` is required before a row can be usable.
- `resolution_rule_source_artifact` records the local Kalshi snapshot used to verify official terms when available.
- The EV hurdle is the captured execution cost basis, not the prettiest screen number.

## Repo Feeds

| Repo | Status | Rows | Usable | EV Readiness | Next Input |
| --- | --- | ---: | ---: | --- | --- |
| `predmarket-alpha` | `predmarket_type2_candidates_loaded_rows_blocked_not_usable` | 52 | 0 | contracts=exact_kalshi_contract_rows_present; terms=verified_official_terms; cost=fee_aware_all_in_cost_present; prob=missing_calibrated_contract_probability; gates=blocked_no_usable_rows | A validated calibrated probability artifact keyed by exact Kalshi ticker/side for the current Type 2 Predmarket rows, not a sportsbook no-vig reference probability. |
| `mlb-platform` | `mlb_type2_candidates_loaded_rows_blocked_not_usable` | 264 | 0 | contracts=exact_kalshi_contract_rows_present; terms=verified_official_terms; cost=fee_aware_all_in_cost_present; prob=missing_calibrated_contract_probability; gates=blocked_no_usable_rows | A model-calibrated probability artifact keyed by exact exchange_market_id/side for MLB Type 2 rows, with timing/mapping gates clean at the row level. |
| `atp-oracle` | `blocked_read_only_atp_no_kalshi_ev_rows` | 0 | 0 | contracts=missing_exact_kalshi_contract_mapping; terms=blocked_until_contract_mapping; cost=blocked_until_kalshi_quote; prob=blocked_fresh_validation_and_external_evidence_missing; gates=blocked_no_contract_rows | Fresh ATP validation/promotion evidence plus D3/G5/P5 external proof and exact Kalshi ticker/side/rules/quote mapping. |
| `nba-analytics-platform` | `blocked_no_kalshi_contract_mapping` | 0 | 0 | contracts=missing_exact_kalshi_contract_mapping; terms=blocked_until_contract_mapping; cost=blocked_until_kalshi_quote; prob=blocked_market_parity_no_current_contract_model; gates=blocked_no_contract_rows | A new source-backed NBA signal or market dataset plus exact Kalshi ticker/side/rules/quote mapping for the target contract class. |
| `nfl_quant_glm51_greenfield` | `nfl_quant_glm51_greenfield_contract_mapping_overlay_usable_ev_rows` | 32 | 12 | contracts=exact_kalshi_contract_rows_present; terms=verified_official_terms; cost=fee_aware_all_in_cost_present; prob=calibrated_contract_probabilities_present; gates=usable_rows_present | A calibrated probability artifact keyed by exact Kalshi ticker/side. |

## Top Row Blockers

- `316`: calibrated contract probability is missing
- `316`: probability source is sportsbook no-vig reference, not a calibrated platform model
- `264`: candidate status is below_threshold
- `264`: repeatability evidence does not support usable contract edges
- `264`: repeatability status is repeatability_no_signal_clean_packets
- `264`: settled validation does not support a policy change
- `264`: settled validation status is settled_validation_no_policy_change_same_slate
- `52`: review status is REVIEW_ONLY_WATCH

## Next Action

Review usable rows manually; execution remains disabled until a separate explicit decision gate exists.
