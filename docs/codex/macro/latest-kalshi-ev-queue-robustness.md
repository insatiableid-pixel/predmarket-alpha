# Kalshi EV Queue Robustness

- Status: `kalshi_ev_queue_robustness_repeat_positive_cost_caveated`
- Research only: `true`
- Execution enabled: `false`
- Distinct snapshots: `2`
- Queue rows: `12`
- Repeat-positive rows: `12`
- Robust candidates: `0`

## Rows

| Rank | Contract | Selection | Snapshots | Positive | Latest Margin | Min Margin | Disposition | Reasons |
| ---: | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| 1 | `KXNFLGAME-26SEP13MIALV-MIA` | `MIA` | 2 | 2 | 0.249735 | 0.249735 | `repeat_positive_cost_caveated` | fee is estimated from executable price |
| 2 | `KXNFLGAME-26SEP14DENKC-DEN` | `DEN` | 2 | 2 | 0.160992 | 0.160992 | `repeat_positive_cost_caveated` | fee is estimated from executable price |
| 3 | `KXNFLGAME-26SEP13TBCIN-TB` | `TB` | 2 | 2 | 0.079303 | 0.079303 | `repeat_positive_cost_caveated` | fee is estimated from executable price |
| 4 | `KXNFLGAME-26SEP13GBMIN-MIN` | `MIN` | 2 | 2 | 0.063783 | 0.063783 | `repeat_positive_cost_caveated` | fee is estimated from executable price |
| 5 | `KXNFLGAME-26SEP13WASPHI-PHI` | `PHI` | 2 | 2 | 0.053433 | 0.053433 | `repeat_positive_cost_caveated` | fee is estimated from executable price |
| 6 | `KXNFLGAME-26SEP13BALIND-IND` | `IND` | 2 | 2 | 0.018837 | 0.018837 | `repeat_positive_cost_caveated` | minimum repeated margin below robust threshold 0.0200; fee is estimated from executable price |
| 7 | `KXNFLGAME-26SEP13NYJTEN-NYJ` | `NYJ` | 2 | 2 | 0.016111 | 0.016111 | `repeat_positive_cost_caveated` | minimum repeated margin below robust threshold 0.0200; fee is estimated from executable price |
| 8 | `KXNFLGAME-26SEP09NESEA-SEA` | `SEA` | 2 | 2 | 0.015845 | 0.015845 | `repeat_positive_cost_caveated` | minimum repeated margin below robust threshold 0.0200; fee is estimated from executable price |
| 9 | `KXNFLGAME-26SEP13BUFHOU-HOU` | `HOU` | 2 | 2 | 0.008208 | 0.008208 | `repeat_positive_cost_caveated` | minimum repeated margin below robust threshold 0.0200; fee is estimated from executable price |
| 10 | `KXNFLGAME-26SEP13ARILAC-ARI` | `ARI` | 2 | 2 | 0.007396 | 0.007396 | `repeat_positive_cost_caveated` | minimum repeated margin below robust threshold 0.0200; fee is estimated from executable price |
| 11 | `KXNFLGAME-26SEP13NODET-DET` | `DET` | 2 | 2 | 0.005822 | 0.005822 | `repeat_positive_cost_caveated` | minimum repeated margin below robust threshold 0.0200; fee is estimated from executable price |
| 12 | `KXNFLGAME-26SEP13ATLPIT-PIT` | `PIT` | 2 | 2 | 0.004023 | 0.004023 | `repeat_positive_cost_caveated` | minimum repeated margin below robust threshold 0.0200; fee is estimated from executable price |

## Next Action

Repeat-positive rows exist, but current robustness is cost-caveated. Next useful input is actual all-in ticket-cost confirmation without order submission, plus forward-context and independent validation.
