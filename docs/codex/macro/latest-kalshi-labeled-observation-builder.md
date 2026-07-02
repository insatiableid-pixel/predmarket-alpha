# Kalshi Labeled Observation Builder

- Status: `labeled_observation_builder_pending_observations_waiting_settlement`
- Pending observations: `44`
- New pending observations: `44`
- Settled markets loaded: `1000`
- Label rows: `0`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `registry_safe` | `pass` | Hypothesis registry is research-only. |
| `ev_ledger_safe` | `pass` | EV ledger is research-only. |
| `pending_observations_available` | `pass` | 44 pending OOS observation(s) available. |
| `settled_markets_available` | `pass` | 1000 settled public market(s) loaded. |
| `label_rows_available` | `blocked` | 0 settled label row(s) emitted. |
| `manual_drop_dirs_outside_repo` | `pass` | Pending and label directories are outside the repo. |
| `no_execution_boundary` | `pass` | Builder emits research-only observation packets and no account/order fields. |

## Blocked Reasons

- `no_registered_contract_ev_hypothesis_match`: `316`
- `pending_contract_not_settled_in_snapshot`: `44`
- `universe_candidate_missing_model_probability`: `6070`

## Guardrail

This builder creates falsification inputs only. It does not test, promote, size, or execute contracts.
