# Sports Stack Sequencing, Ghost Depth, And Flow/Liquidity Families

Date: 2026-07-04

## Objective

Act on the sequencing memo:

- Near term: World Cup/FIFA first, MLB second, ATP next; NFL is preseason-watch, NBA is offseason/deprioritized.
- Keep adaptation at the output/gate layer, not the feature layer.
- Re-run current-depth ghost-listing diagnostics before locking `cap_i`.
- Register near-resolution informed flow and passive liquidity provision as separate falsification-gated families.
- Keep economics and politics in slower base-rate accumulation.

## Landing

Added `scripts/kalshi_ghost_listing_depth_diagnostic.py` and `make kalshi-ghost-listing-depth-diagnostic`.

Latest current-depth diagnostic:

- Status: `ghost_listing_depth_diagnostic_current_depth_ready`
- Selected current candidates: `120`
- Current public orderbooks captured: `120`
- Probe coverage: `1.0`
- Positive-depth fraction: `1.0`
- Ghost-listing fraction: `0.0`
- `cap_i_lock_allowed`: `true`
- Raw public orderbook snapshots stayed outside the repo under `/home/mrwatson/manual_drops/kalshi_ghost_listing_depth/`.

Added `scripts/kalshi_sports_stack_sequencing.py` and `make kalshi-sports-stack-sequencing`.

Latest sports sequencing:

- Status: `sports_stack_sequencing_ready_current_depth_passed`
- Recommended order: `world_cup_soccer -> mlb -> atp -> nfl -> nba`
- Near-term active candidates: `3109`
- Current counts: `78` World Cup/FIFA, `2935` MLB, `96` ATP
- NBA is explicitly offseason/deprioritized; NFL is preseason-watch.
- Every sports row says `adaptation_layer=output_layer_only`.

Extended `scripts/kalshi_hypothesis_registry.py`:

- `near_resolution_informed_flow`
  - Metric: `pre_close_flow_lead_lag_survival`
  - Acceptance: OOS/FDR survival for pre-close flow or quote imbalance, after fees and stale-source filters.
- `passive_liquidity_provision`
  - Metric: `maker_fill_net_ev_after_adverse_selection`
  - Acceptance: OOS/FDR survival for maker-fill EV after non-fill, timeout, fees, and adverse-selection costs.

Latest hypothesis registry:

- Status: `hypothesis_registry_ready_falsification_blocked_missing_labeled_oos_evidence`
- Hypotheses: `57`
- `near_resolution_informed_flow`: `8`
- `passive_liquidity_provision`: `9`

Wired the new artifacts into the command center:

- `scripts/kalshi_signal_factory_status.py` now consumes ghost-depth + sports-stack sequencing paths through the hermetic `Artifacts` bundle.
- `scripts/codex_macro_router.py` now recognizes:
  - `signal_factory_sports_stack_sequencing_ready_current_depth_passed`
  - `signal_factory_sports_stack_sequencing_ready_cap_i_lock_blocked`
- Latest signal-factory status: `signal_factory_sports_stack_sequencing_ready_current_depth_passed`
- Latest macro-route recommendation: run the family-specific near-term sports evidence loop in order: World Cup/FIFA, MLB, ATP.

World Cup evidence was refreshed:

- Observation loop: `world_cup_proxy_observation_loop_ready_waiting_settlement`
- Total World Cup observations: `193`
- Current new observations: `78`
- Settled labels: `0`
- Falsification: `world_cup_proxy_feature_model_falsification_blocked_missing_labels`

## Guardrails

No execution behavior was enabled or loosened.

- `research_only=true`
- `execution_enabled=false`
- `market_execution=false`
- `account_or_order_paths=false`
- `usable=false`
- No paper stake, live order, account path, or tradable claim was introduced.

## Verification

- Focused router/status/sequencing/depth/registry tests: `102 passed`
- `make test-unit`: `686 passed, 14 deselected`
- `make test-integration`: `14 passed`
- `make lint-baseline-check`: `OK lint 1407/1422 format 88/94`
- `make tech-debt-check`: `OK 22/22`
- `make file-sizes-check`: `OK no new oversized files`
- `make modularize`: `2 kept, 0 broken`
- `make quality`: exits `0`; advisory Ruff/deptry debt remains under the existing ratchet/baseline model.

## Next

Run the near-term sports evidence loop mechanically:

1. World Cup/FIFA observation accumulation and settlement labels.
2. MLB observation/label/falsification chain.
3. ATP observation/evidence gate once settlement labels arrive.
4. Keep NFL bridge warm for preseason.
5. Keep NBA deprioritized until fall liquidity returns.

Do not lock capacity from stale or inventory-only depth. Do not merge sport feature layers.
