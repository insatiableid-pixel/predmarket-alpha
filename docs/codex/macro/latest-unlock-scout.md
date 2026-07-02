# Macro Unlock Scout

- As of UTC: `2026-07-01T19:26:37Z`
- Mode: review-only
- Provider/API calls: false
- Market execution: false
- All lanes parked: `false`

## Local Inputs

- `manual_drops`: `/home/mrwatson/manual_drops`
- `odds_api_json_count`: `16`
- `kalshi_json_count`: `8`
- `predmarket_reference_exists`: `True`
- `kalshi_ev_probability_overlay_count`: `1`
- `kalshi_ev_contract_mapping_overlay_count`: `1`

## Kalshi EV

- Ledger status: `kalshi_ev_ledger_ready_with_usable_contract_edges`
- Overlay preflight status: `overlay_preflight_usable_ev_rows_present`
- Calibration work order status: `calibration_work_order_ready_source_gated`
- Contract mapping work order status: `contract_mapping_work_order_ready`
- Local contract evidence scout status: `local_contract_evidence_ready_for_overlay_fill`
- NFL overlay assembler status: `nfl_overlay_assembler_overlays_written`

## Lanes

### predmarket-alpha

- Status: `local_contract_evidence_ready_for_overlay_fill`
- Blocked: `false`
- What exists: ev_ledger_status=kalshi_ev_ledger_ready_with_usable_contract_edges, ledger_rows=348, usable_rows=12, nfl_mapping_sides=32, source_model_rows=16, local_contract_evidence_status=local_contract_evidence_ready_for_overlay_fill, nfl_contract_evidence_rows=164, ready_target_matches=172, overlay_assembler_status=nfl_overlay_assembler_overlays_written, assembled_overlay_pairs=32
- Missing input: No new external input is needed for the ready target match; fill matching safe overlays outside the repo, then rerun preflight and ledger.
- Next local command: `make kalshi-ev-contract-mapping-work-order && make kalshi-ev-local-contract-evidence-scout && make kalshi-ev-nfl-overlay-assembler && make kalshi-ev-overlay-preflight && make kalshi-ev-ledger`

### mlb-platform

- Status: `betexplorer_market_closing_comparison_ready_no_policy_change`
- Blocked: `true`
- What exists: odds_api_json_files=16, kalshi_json_files=8, latest_intake_status=ready_pregame_pair, latest_intake_ready=True, latest_intake_blockers=0, latest_intake_report=/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/2026-06-29-late-current-clean-subset-intake/pregame-drop-intake-status.json, latest_repeatability_status=repeatability_no_signal_clean_packets, clean_packets=0, clean_no_signal_packets=4, repeated_descriptors=0, latest_repeatability_report=/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-repeatability-ledger-latest/type2-repeatability-ledger.json, latest_repeatability_research_review_status=repeatability_research_review_blocked_threshold_not_met, stable_recurring_descriptors=0, same_slate_dates=[], latest_repeatability_research_review_report=/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-repeatability-research-review-latest/type2-repeatability-research-review.json, latest_threshold_policy_status=threshold_policy_hold_current, current_threshold_count=0, max_abs_net_edge=0.02772647053226107, same_slate_date_count=1, best_lower_threshold=0.02, latest_threshold_policy_report=/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-threshold-policy-review-latest/type2-threshold-policy-review.json, latest_settled_validation_status=settled_validation_no_policy_change_same_slate, valid_directional_rows=1239, directional_correct_rate=45.0%, current_threshold_count=0, same_slate_date_count=1, latest_settled_validation_report=/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-settled-outcome-validation-latest/type2-settled-outcome-validation.json, latest_closing_proxy_status=closing_proxy_same_slate_support_insufficient, paired_rows=819, current_threshold_count=0, same_slate_date_count=1, best_lower_threshold=0.025, best_lower_support=6, best_lower_against=0, latest_closing_proxy_report=/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-closing-proxy-validation-latest/type2-closing-proxy-validation.json, latest_betexplorer_moneyline_status=betexplorer_moneyline_closing_comparison_ready_no_policy_change, matched_rows=22, current_threshold_count=0, converged=16, diverged=6, direction_support=17, direction_against=5, latest_betexplorer_moneyline_report=/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-betexplorer-moneyline-closing-comparison-latest/type2-betexplorer-moneyline-closing-comparison.json, latest_betexplorer_market_status=betexplorer_market_closing_comparison_ready_no_policy_change, matched_rows=24, matched_by_market={'ml': 22, 'run_line': 2}, current_threshold_count=0, converged=16, diverged=8, direction_support=18, direction_against=6, latest_betexplorer_market_report=/home/mrwatson/projects/mlb-platform/docs/codex/artifacts/type2-betexplorer-market-closing-comparison-latest/type2-betexplorer-market-closing-comparison.json
- Missing input: Public BetExplorer multi-market comparison is present and date-matched, but it is still narrow, has zero current-threshold rows, and does not justify a policy change. Next evidence is broader book/line/source coverage, an independent clean slate, or stronger true closing-line validation.
- Next local command: `cd /home/mrwatson/projects/mlb-platform && make macro-status`

### atp-oracle

- Status: `blocked_g1g2_model_quality_evidence`
- Blocked: `true`
- What exists: diagnostic_status=blocked_g1g2_model_quality_evidence, vision_score=93
- Missing input: Fresh validation/promotion evidence plus D3/G5/P5 external proof (3 blockers).
- Next local command: `cd /home/mrwatson/projects/atp-oracle && make type2-g1g2-diagnostic`

### nba-analytics-platform

- Status: `macro_partial_truth_shrinkage_clipped_residual_market_parity`
- Blocked: `true`
- What exists: router_priority=-11, gate_counts={'blocked': 3, 'fail': 0, 'pass': 11, 'warn': 0}
- Missing input: New source-backed NBA signal or market dataset that can beat the current market-parity baseline; do not run new residual variants without that input.
- Next local command: `cd /home/mrwatson/projects/nba-analytics-platform && make macro-status`

### nfl_quant_glm51_greenfield

- Status: `line_readiness_profiled_slate_forward_context_not_yet_due_research_only`
- Blocked: `true`
- What exists: router_priority=-5, gate_counts={'blocked': 0, 'fail': 0, 'pass': 11, 'warn': 4}
- Missing input: Forward-context evidence when due or manually dropped outside the repo: injuries, weather, official starting QBs/depth chart changes, and closing/reference line evidence. Current availability says these inputs are not yet due.
- Next local command: `cd /home/mrwatson/projects/nfl_quant_glm51_greenfield && make forward-context-availability && make macro-status`

## Guardrail

This scout only summarizes local evidence and next local commands. It does not authorize execution or account activity.
