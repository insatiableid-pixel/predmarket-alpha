# MLB Dense Fixed-Clock Panel Registration

- Panel family: `sports_mlb_dense_fixed_clock_panel_v1`
- Registration version: `mlb_dense_panel_registration_v1`
- Generated: `2026-07-10T05:49:31.502399Z`
- Registration hash: `553135d7d1456aeda4a9115784aa423b81931cceed4d2a2f707b5ca8dcbe816e`
- Research only: `True`

## Primary clocks

- Primary: `{'T-60m': 3600, 'T-15m': 900}`
- Primary staleness: `{'T-60m': 300, 'T-15m': 120}`
- Secondary: `{'T-24h': 86400, 'T-6h': 21600}`

## Panel readiness gates

- `min_distinct_slate_dates`: `10`
- `min_distinct_events_overall`: `120`
- `min_eligible_events_per_primary_clock`: `100`
- `min_independent_slates_per_tested_candidate`: `8`
- `max_largest_slate_share`: `0.2`
- `zero_unhandled_duplicates_complements_lookahead`: `True`
- `complete_settlement_provenance_for_labeled_inference`: `True`

## Frozen candidates (exact; do not retune)

- `tight_spread_favorite_buy_yes_t60m` clock=`T-60m` side=`yes` feature=`p_hat` threshold=`0.62` spread_max=`0.03` formula_hash=`9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d` registered=`2026-07-10T05:37:38Z`

## Operating rules

- No outcome-conditioned threshold search until `evidence_panel_ready`.
- Frozen candidates evaluated once at preregistered confirmation power only.
- At most one distinct v2 family after frozen-candidate resolution.
- No live execution, sizing, accounts, orders, or credentials.
