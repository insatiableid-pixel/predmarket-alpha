# Kalshi Crypto Proxy Correlation Cluster Control

- Status: `crypto_proxy_correlation_cluster_control_blocked_upstream_ccd`
- Positive clusters: `0`
- Required positive clusters: `3`
- Total positive-depth cost: `0.0`
- Total controlled-depth cost: `0.0`
- Largest positive cluster share: `None`
- Largest controlled cluster share: `None`
- Usable rows: `0`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `ccd_report_ready` | `pass` | CCD status is crypto_proxy_capacity_correlation_decay_blocked_no_current_candidates. |
| `upstream_capacity_and_decay_pass` | `blocked` | Capacity status capacity_depth_missing_or_not_positive; decay status decay_survival_blocked. |
| `positive_cluster_breadth` | `blocked` | 0 positive cluster(s); requires 3. |
| `controlled_cluster_share_limit` | `blocked` | Largest controlled cluster share None; max is 0.35. |
| `no_usable_sizing_or_execution` | `pass` | Cluster-control report remains research-only with zero usable rows and no sizing or execution. |

## Next Action

- Name: `kalshi_crypto_proxy_correlation_cluster_control_audit`
- Why: Cluster control is blocked by missing or upstream-invalid CCD evidence.
- Stop condition: Stop before paper overlay, sizing, execution, or account/order paths.

## Guardrail

This report is not a betting recommendation and never authorizes sizing or execution.
