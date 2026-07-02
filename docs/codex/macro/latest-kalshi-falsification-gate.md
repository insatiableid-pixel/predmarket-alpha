# Kalshi Falsification Gate

- Status: `falsification_gate_blocked_missing_labeled_oos_evidence`
- Registered hypotheses: `36`
- Tested hypotheses: `0`
- Promoted hypotheses: `0`

| Gate | Status | Reason |
| --- | --- | --- |
| `universe_inventory_safe` | `pass` | Universe inventory is research-only and available. |
| `hypothesis_registry_nonempty` | `pass` | 36 hypothesis candidate(s) generated. |
| `contract_ev_cost_surface_available` | `pass` | EV ledger is available for all-in break-even costs. |
| `labeled_oos_evidence_available` | `blocked` | No labeled outcomes/backtest packet exists for these hypothesis IDs. |
| `walk_forward_or_purged_split` | `blocked` | No time-safe split packet exists; random/k-fold validation is not acceptable. |
| `fdr_multiple_testing_control` | `blocked` | No Benjamini-Hochberg/BY or equivalent q-value packet exists for the tested family. |
| `promotion_disabled_until_falsified` | `pass` | All generated hypotheses remain candidate_unvalidated. |

No hypothesis may promote without labeled OOS evidence, time-safe validation, FDR correction, and cost-aware survival.
