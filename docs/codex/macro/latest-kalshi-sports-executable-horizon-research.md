# Kalshi Sports Executable Horizon Research

- Status: `executable_horizon_research_family_falsified`
- Family status: `falsified`
- Observations: `11061`
- Executable labels: `3584`
- Censored labels: `29119`
- Pre-registered candidates: `26`
- Testable candidates: `15`
- FDR survivors: `0`
- Research-ready: `0`
- Best model: `tight_spread_imbalance_buy_yes_h900` q=`None` mean_net=`-0.0197865385` oos_events=`52`
- Untouched cutoff: `2026-07-10T04:45:54Z`

## Decision

Declared executable-horizon family falsified on available discovery evidence. Advance to the next distinct sports family or densify labels; do not tune on holdout.

## Evaluations

- `spread_norm_imbalance_buy_yes_h300` status=`insufficient_sample` oos=`85` mean_net=`-0.0659905882` q=`None` negctrl=`False`
- `spread_norm_imbalance_buy_no_h300` status=`testable` oos=`217` mean_net=`-0.0506502304` q=`1.0` negctrl=`False`
- `microprice_momentum_buy_yes_h300` status=`insufficient_sample` oos=`94` mean_net=`-0.1011510638` q=`None` negctrl=`False`
- `microprice_momentum_buy_no_h300` status=`insufficient_sample` oos=`92` mean_net=`-0.1003543478` q=`None` negctrl=`False`
- `microprice_mid_gap_fade_yes_h300` status=`testable` oos=`141` mean_net=`-0.0724205674` q=`1.0` negctrl=`False`
- `microprice_mid_gap_fade_no_h300` status=`testable` oos=`206` mean_net=`-0.0764597087` q=`1.0` negctrl=`False`
- `depth_delta_buy_yes_h900` status=`testable` oos=`136` mean_net=`-0.0664448529` q=`1.0` negctrl=`False`
- `depth_delta_buy_no_h900` status=`testable` oos=`140` mean_net=`-0.068605` q=`1.0` negctrl=`False`
- `tight_spread_imbalance_buy_yes_h900` status=`insufficient_sample` oos=`52` mean_net=`-0.0197865385` q=`None` negctrl=`False`
- `tight_spread_imbalance_buy_no_h900` status=`testable` oos=`173` mean_net=`-0.046799422` q=`1.0` negctrl=`False`
- `negctrl_time_reversed_imbalance_h300` status=`insufficient_sample` oos=`56` mean_net=`-0.0877767857` q=`None` negctrl=`True`
- `negctrl_impossible_mid_delta_sign_flip_h300` status=`testable` oos=`105` mean_net=`-0.0802380952` q=`1.0` negctrl=`True`
- `peer_imbalance_gap_buy_yes_h300` status=`testable` oos=`141` mean_net=`-0.0917141844` q=`1.0` negctrl=`False`
- `peer_imbalance_gap_buy_no_h300` status=`testable` oos=`135` mean_net=`-0.0767948148` q=`1.0` negctrl=`False`
- `peer_max_delta_follow_yes_h900` status=`testable` oos=`124` mean_net=`-0.0604717742` q=`1.0` negctrl=`False`
- `peer_min_delta_follow_no_h900` status=`testable` oos=`123` mean_net=`-0.0772658537` q=`1.0` negctrl=`False`
- `peer_microprice_lead_buy_yes_h300` status=`insufficient_sample` oos=`92` mean_net=`-0.0891586957` q=`None` negctrl=`False`
- `peer_microprice_lead_buy_no_h300` status=`insufficient_sample` oos=`98` mean_net=`-0.0776867347` q=`None` negctrl=`False`
- `negctrl_anti_peer_gap_h300` status=`testable` oos=`135` mean_net=`-0.0722177778` q=`1.0` negctrl=`True`
- `negctrl_random_peer_sign_h900` status=`testable` oos=`138` mean_net=`-0.0651746377` q=`1.0` negctrl=`True`
- `thin_imbalance_fade_yes_h900` status=`insufficient_sample` oos=`1` mean_net=`-0.2446` q=`None` negctrl=`False`
- `thin_imbalance_fade_no_h900` status=`insufficient_sample` oos=`3` mean_net=`-0.0626666667` q=`None` negctrl=`False`
- `thin_imbalance_fade_yes_h300` status=`insufficient_sample` oos=`2` mean_net=`-0.1838` q=`None` negctrl=`False`
- `abs_imbalance_fade_no_h300` status=`testable` oos=`132` mean_net=`-0.0880613636` q=`1.0` negctrl=`False`
- `abs_imbalance_fade_yes_h300` status=`testable` oos=`120` mean_net=`-0.0981133333` q=`1.0` negctrl=`False`
- `negctrl_thin_momentum_h900` status=`insufficient_sample` oos=`1` mean_net=`-0.3474` q=`None` negctrl=`True`

## Frontier

- rank `1` `executable_horizon_microstructure_v1` status=`falsified` next=`Retire family if complete FDR failure; else densify 5/15m capture`
- rank `2` `tick_recorder_dense_mlb_orderbook` status=`discovery_pending` next=`Run read-only tick recorder on MLB moneyline books during live slate`
- rank `3` `cross_contract_within_event_coherence` status=`falsified` next=`Retired on discovery FDR; densify ticks or park`
- rank `4` `thin_book_fade` status=`falsified` next=`Retired on discovery FDR; densify ticks or park`
- rank `5` `atp_forward_oos_and_settlement_velocity` status=`calendar_monitor` next=`Parked monitor only`
- rank `6` `asian_sharp_soccer` status=`blocked_external_deferred` next=`Do not pursue under this directive`

Research-only. No paper stake, sizing, accounts, orders, or live execution.
