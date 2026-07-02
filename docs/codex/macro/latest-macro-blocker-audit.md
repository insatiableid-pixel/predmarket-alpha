# Macro Blocker Audit

- Status: `macro_blocker_audit_incomplete`
- Research only: `true`
- Lanes: `5`
- Blocked lanes: `4`
- Specific missing-input lanes: `5`
- Usable EV rows: `12`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `unlock_scout_present` | `pass` | Loaded 5 lane(s) from /home/mrwatson/projects/predmarket-alpha/docs/codex/macro/latest-unlock-scout.json. |
| `all_lanes_marked_blocked` | `blocked` | At least one unlock-scout lane is not marked blocked. |
| `all_missing_inputs_specific` | `pass` | Every lane has a named missing input. |
| `all_next_commands_present` | `pass` | Every lane has a next local command. |
| `no_usable_ev_rows` | `blocked` | Usable EV ledger rows: 12. |
| `no_overlay_rows_written_without_evidence` | `blocked` | NFL overlay assembler wrote overlays; ledger/preflight must be reviewed instead of declaring blocked. |
| `no_ready_nfl_target_contract_evidence` | `blocked` | Ready NFL target contract matches: 172. |
| `research_only_safety` | `pass` | Unlock scout and EV ledger are research-only and execution-disabled. |

## Lane Proof

| Repo | Status | Proof | Missing Input | Next Command |
| --- | --- | --- | --- | --- |
| `predmarket-alpha` | `local_contract_evidence_ready_for_overlay_fill` | `blocked` | No new external input is needed for the ready target match; fill matching safe overlays outside the repo, then rerun preflight and ledger. | `make kalshi-ev-contract-mapping-work-order && make kalshi-ev-local-contract-evidence-scout && make kalshi-ev-nfl-overlay-assembler && make kalshi-ev-overlay-preflight && make kalshi-ev-ledger` |
| `mlb-platform` | `betexplorer_market_closing_comparison_ready_no_policy_change` | `pass` | Public BetExplorer multi-market comparison is present and date-matched, but it is still narrow, has zero current-threshold rows, and does not justify a policy change. Next evidence is broader book/line/source coverage, an independent clean slate, or stronger true closing-line validation. | `cd /home/mrwatson/projects/mlb-platform && make macro-status` |
| `atp-oracle` | `blocked_g1g2_model_quality_evidence` | `pass` | Fresh validation/promotion evidence plus D3/G5/P5 external proof (3 blockers). | `cd /home/mrwatson/projects/atp-oracle && make type2-g1g2-diagnostic` |
| `nba-analytics-platform` | `macro_partial_truth_shrinkage_clipped_residual_market_parity` | `pass` | New source-backed NBA signal or market dataset that can beat the current market-parity baseline; do not run new residual variants without that input. | `cd /home/mrwatson/projects/nba-analytics-platform && make macro-status` |
| `nfl_quant_glm51_greenfield` | `line_readiness_profiled_slate_forward_context_not_yet_due_research_only` | `pass` | Forward-context evidence when due or manually dropped outside the repo: injuries, weather, official starting QBs/depth chart changes, and closing/reference line evidence. Current availability says these inputs are not yet due. | `cd /home/mrwatson/projects/nfl_quant_glm51_greenfield && make forward-context-availability && make macro-status` |

## Next Action

Blocker proof is incomplete for: predmarket-alpha.
