# Kalshi Sports MLB Settlement Miscalibration

- Status: `mlb_settlement_miscalibration_confirmation_pending`
- Family status: `confirmation_pending`
- Family: `sports_mlb_settlement_miscalibration_v1`
- Schema: `2` (`mlb_settlement_miscalibration_inference_v2`)
- Observations: `26039`
- Settlement tickers: `1774`
- Labeled rows: `1168`
- Distinct events: `175`
- Pre-registered candidates: `11`
- Powered novel: `1`
- Underpowered novel: `6`
- Powered falsified: `0`
- Frozen multi-slate confirmation: `1`
- FDR survivors (incl. frozen/pending): `1`
- Research-ready survivors: `0`
- Historical discovery data cutoff: `2026-07-10T05:18:29Z`
- Cutoff provenance: `runtime_censor_of_historical_labels_not_pre_outcome_preregistration`
- Forward confirmation registered at: `2026-07-10T05:37:38Z`
- Capture infrastructure ready: `True`
- Evidence panel ready: `False`
- Capture/panel status: `capture_infrastructure_ready_panel_insufficient_slate_breadth`
- Public market fetches: `False`

## Decision

Corrected discovery inference produced frozen/confirmation-pending candidate(s). Hold formulas fixed; accumulate multi-slate dense panel for independent confirmation.

## Power (per-specification)

- Panel event coverage met: `True`
- Family-wide discovery power met: `False`
- Events by clock: `{'T-24h': 169, 'T-6h': 169, 'T-60m': 168, 'T-15m': 100}`
- Slates by clock: `{'T-24h': 14, 'T-6h': 14, 'T-60m': 14, 'T-15m': 13}`
- Powered novel count: `1`
- Underpowered novel count: `6`

## Calibration

- `T-24h` n=`324` events=`169` mean_residual=`-0.0052232732` mean_brier=`0.2423907029`
- `T-6h` n=`322` events=`169` mean_residual=`-0.0042632509` mean_brier=`0.2428799792`
- `T-60m` n=`321` events=`166` mean_residual=`0.0026440519` mean_brier=`0.1136740262`
- `T-15m` n=`181` events=`92` mean_residual=`-3.61693e-05` mean_brier=`0.0780349046`

## Evaluations

- `baseline_static_longshot_buy_yes_t60m` status=`underpowered` oos_events=`1` oos_slates=`1` mean_net=`-0.2942` mean_resid=`-0.2760510605` p_econ=`1.0` p_cal=`1.0` p_joint=`1.0` q=`None` slate_share=`1.0` negctrl=`False` baseline=`True`
- `baseline_static_favorite_buy_yes_t60m` status=`underpowered` oos_events=`3` oos_slates=`1` mean_net=`0.1604666667` mean_resid=`0.1789319121` p_econ=`0.5002498751` p_cal=`0.5002498751` p_joint=`0.5002498751` q=`None` slate_share=`1.0` negctrl=`False` baseline=`True`
- `clock_x_price_fade_favorite_t60m` status=`underpowered` oos_events=`19` oos_slates=`6` mean_net=`-0.1060052632` mean_resid=`-0.0970911641` p_econ=`1.0` p_cal=`1.0` p_joint=`1.0` q=`None` slate_share=`0.5263157895` negctrl=`False` baseline=`False`
- `clock_x_price_buy_underdog_t6h` status=`underpowered` oos_events=`2` oos_slates=`2` mean_net=`-0.36585` mean_resid=`-0.3453727588` p_econ=`1.0` p_cal=`1.0` p_joint=`1.0` q=`None` slate_share=`0.5` negctrl=`False` baseline=`False`
- `listing_age_cold_start_fade_extreme_t24h` status=`underpowered` oos_events=`0` oos_slates=`0` mean_net=`None` mean_resid=`None` p_econ=`1.0` p_cal=`1.0` p_joint=`1.0` q=`None` slate_share=`0.0` negctrl=`False` baseline=`False`
- `path_slope_reversion_buy_no_t60m` status=`underpowered` oos_events=`23` oos_slates=`6` mean_net=`-0.1584086957` mean_resid=`-0.1612345018` p_econ=`1.0` p_cal=`1.0` p_joint=`1.0` q=`None` slate_share=`0.5217391304` negctrl=`False` baseline=`False`
- `path_slope_continuation_buy_yes_t60m` status=`underpowered` oos_events=`21` oos_slates=`5` mean_net=`0.1465952381` mean_resid=`0.1612345018` p_econ=`0.0004997501` p_cal=`0.0004997501` p_joint=`0.0004997501` q=`None` slate_share=`0.5714285714` negctrl=`False` baseline=`False`
- `clock_geometry_drift_fade_t15m` status=`underpowered` oos_events=`23` oos_slates=`4` mean_net=`-0.0326782609` mean_resid=`-0.0256521146` p_econ=`1.0` p_cal=`1.0` p_joint=`1.0` q=`None` slate_share=`0.3913043478` negctrl=`False` baseline=`False`
- `tight_spread_favorite_buy_yes_t60m` status=`frozen_candidate_waiting_multi_slate_confirmation` oos_events=`20` oos_slates=`6` mean_net=`0.094615` mean_resid=`0.1076245857` p_econ=`0.0004997501` p_cal=`0.0004997501` p_joint=`0.0004997501` q=`0.0004997501` slate_share=`0.5` negctrl=`False` baseline=`False`
- `negctrl_trade_against_path_slope_t60m` status=`underpowered` oos_events=`24` oos_slates=`6` mean_net=`-0.1316` mean_resid=`-0.1278975355` p_econ=`1.0` p_cal=`1.0` p_joint=`1.0` q=`None` slate_share=`0.5` negctrl=`True` baseline=`False`
- `negctrl_always_buy_yes_t60m` status=`testable` oos_events=`27` oos_slates=`7` mean_net=`-0.0530592593` mean_resid=`-0.0383528724` p_econ=`1.0` p_cal=`1.0` p_joint=`1.0` q=`None` slate_share=`0.4444444444` negctrl=`True` baseline=`False`

## Frozen candidates (exact; do not retune)

- `tight_spread_favorite_buy_yes_t60m` formula_hash=`9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d` clock=`T-60m` side=`yes` registered=`2026-07-10T05:37:38Z`

## Confirmation

- `baseline_static_longshot_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `baseline_static_favorite_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `clock_x_price_fade_favorite_t60m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `clock_x_price_buy_underdog_t6h` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `listing_age_cold_start_fade_extreme_t24h` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `path_slope_reversion_buy_no_t60m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `path_slope_continuation_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `clock_geometry_drift_fade_t15m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `tight_spread_favorite_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `negctrl_trade_against_path_slope_t60m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`
- `negctrl_always_buy_yes_t60m` status=`confirmation_insufficient_sample` events=`0` slates=`0` mean_net=`None`

## Frontier

- rank `1` `sports_mlb_settlement_miscalibration_v1` status=`confirmation_pending` next=`Hold frozen candidates fixed; accumulate multi-slate dense fixed-clock panel for independent confirmation; do not retune`
- rank `2` `mlb_multiweek_dense_fixed_clock_panel_v2` status=`discovery_pending` next=`Run scripts/kalshi_sports_mlb_dense_book_capture.py on a cadence covering primary T-60m/T-15m clocks across >=10 chronological slates before confirmation`
- rank `3` `sports_exact_cross_contract_moneyline_coherence` status=`parked` next=`Park until multi-week dense panel exists; do not mix with v1 retunes`
- rank `4` `retired_short_horizon_microstructure` status=`falsified` next=`Parked permanently under negative registry`

Research-only. No paper stake, sizing, accounts, orders, or live execution.
