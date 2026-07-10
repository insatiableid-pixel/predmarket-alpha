# MLB Dense-Panel Single-Shot Confirmation Contract

- Contract: `mlb_dense_panel_single_shot_confirmation_v1`
- Registered: `2026-07-10T06:35:42Z`
- Contract hash: `306d226da9679b33011d44e31f239a1a57cc4ec27a9ef3eb90a9988265d403be`
- Panel registration hash: `553135d7d1456aeda4a9115784aa423b81931cceed4d2a2f707b5ca8dcbe816e`
- Candidate: `tight_spread_favorite_buy_yes_t60m`
- Formula hash: `9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d`
- Clock / side: `T-60m` / `yes`
- Threshold / spread max: `0.62` / `0.03`
- Minimum events / slates: `15` / `8`
- Maximum slate share: `0.2`
- Inference: `max(p_economic,p_calibration)`; alpha=`0.05`

The candidate sample is frozen before settlement fetches. Interrupted runs
resume the same sample; finalized results are idempotent and immutable.

Research-only. No paper/live promotion, sizing, accounts, or orders.
