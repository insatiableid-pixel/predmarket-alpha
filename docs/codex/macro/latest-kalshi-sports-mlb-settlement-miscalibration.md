# Kalshi Sports MLB Settlement Miscalibration

- Status: `mlb_settlement_miscalibration_family_falsified`
- Family status: `falsified`
- Family: `sports_mlb_settlement_miscalibration_v1`
- Observations: `26219`
- Settlement tickers: `1774`
- Labeled rows: `1168`
- Distinct events: `175`
- Pre-registered candidates: `11`
- Testable candidates: `6`
- FDR survivors: `0`
- Research-ready: `0`
- Discovery cutoff: `2026-07-10T05:18:29Z`
- Public market fetches: `False`

## Decision

Outcome B: finite family tested at pre-registered power with no survivor. Record negative evidence and do not retune cosmetically.

## Power

- Discovery power met: `True`
- Events by clock: `{'T-24h': 169, 'T-6h': 169, 'T-60m': 168, 'T-15m': 100}`

## Calibration

- `T-24h` n=`324` events=`169` mean_residual=`-0.0052232732` mean_brier=`0.2423907029`
- `T-6h` n=`322` events=`169` mean_residual=`-0.0042632509` mean_brier=`0.2428799792`
- `T-60m` n=`321` events=`166` mean_residual=`0.0026440519` mean_brier=`0.1136740262`
- `T-15m` n=`181` events=`92` mean_residual=`-3.61693e-05` mean_brier=`0.0780349046`

## Evaluations

- `baseline_static_longshot_buy_yes_t60m` status=`insufficient_sample` oos=`1` mean_net=`-0.2942` mean_resid=`-0.2760510605` q=`None` negctrl=`False` baseline=`True`
- `baseline_static_favorite_buy_yes_t60m` status=`insufficient_sample` oos=`3` mean_net=`0.1604666667` mean_resid=`0.1789319121` q=`None` negctrl=`False` baseline=`True`
- `clock_x_price_fade_favorite_t60m` status=`insufficient_sample` oos=`19` mean_net=`-0.1060052632` mean_resid=`-0.0970911641` q=`None` negctrl=`False` baseline=`False`
- `clock_x_price_buy_underdog_t6h` status=`insufficient_sample` oos=`2` mean_net=`-0.36585` mean_resid=`-0.3453727588` q=`None` negctrl=`False` baseline=`False`
- `listing_age_cold_start_fade_extreme_t24h` status=`insufficient_sample` oos=`0` mean_net=`None` mean_resid=`None` q=`None` negctrl=`False` baseline=`False`
- `path_slope_reversion_buy_no_t60m` status=`falsified` oos=`23` mean_net=`-0.1584086957` mean_resid=`-0.1612345018` q=`1.0` negctrl=`False` baseline=`False`
- `path_slope_continuation_buy_yes_t60m` status=`falsified` oos=`21` mean_net=`0.1465952381` mean_resid=`0.1612345018` q=`2.8608e-06` negctrl=`False` baseline=`False`
- `clock_geometry_drift_fade_t15m` status=`falsified` oos=`23` mean_net=`-0.0326782609` mean_resid=`-0.0256521146` q=`1.0` negctrl=`False` baseline=`False`
- `tight_spread_favorite_buy_yes_t60m` status=`falsified` oos=`20` mean_net=`0.094615` mean_resid=`0.1076245857` q=`2.8611e-06` negctrl=`False` baseline=`False`
- `negctrl_trade_against_path_slope_t60m` status=`falsified` oos=`24` mean_net=`-0.1316` mean_resid=`-0.1278975355` q=`1.0` negctrl=`True` baseline=`False`
- `negctrl_always_buy_yes_t60m` status=`falsified` oos=`27` mean_net=`-0.0530592593` mean_resid=`-0.0383528724` q=`1.0` negctrl=`True` baseline=`False`

## Confirmation

- `baseline_static_longshot_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `baseline_static_favorite_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `clock_x_price_fade_favorite_t60m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `clock_x_price_buy_underdog_t6h` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `listing_age_cold_start_fade_extreme_t24h` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `path_slope_reversion_buy_no_t60m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `path_slope_continuation_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `clock_geometry_drift_fade_t15m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `tight_spread_favorite_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `negctrl_trade_against_path_slope_t60m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`
- `negctrl_always_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` mean_net=`None`

## Frontier

- rank `1` `sports_mlb_settlement_miscalibration_v1` status=`falsified` next=`Retired: do not retune thresholds/buckets; require multi-week dense orderbook panel as a new pre-registered evidence surface before reopening`
- rank `2` `mlb_multiweek_dense_fixed_clock_panel_v2` status=`discovery_pending` next=`Run scripts/kalshi_sports_mlb_dense_book_capture.py on a cadence covering T-24h/T-6h/T-60m/T-15m across >=4 chronological slates before re-registering`
- rank `3` `sports_exact_cross_contract_moneyline_coherence` status=`parked` next=`Park until multi-week dense panel exists; do not mix with retired v1`
- rank `4` `retired_short_horizon_microstructure` status=`falsified` next=`Parked permanently under negative registry`

Research-only. No paper stake, sizing, accounts, orders, or live execution.
