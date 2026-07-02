# Kalshi EV NFL Overlay Assembler

- Status: `nfl_overlay_assembler_overlays_written`
- Research only: `true`
- Ready target matches: `32`
- Assembled overlay pairs: `32`
- Overlays written: `true`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `research_only_no_live_calls` | `pass` | Assembler consumes local scout/work-order JSON only; live/provider calls are not implemented. |
| `scout_present_safe` | `pass` | Scout artifact is present and research-only. |
| `contract_mapping_work_order_present` | `pass` | Loaded 32 work-order target side(s). |
| `ready_local_target_evidence_present` | `pass` | Found 32 ready local target match(es). |
| `overlay_rows_assembled` | `pass` | Assembled 32 overlay pair(s). |
| `overlay_output_dirs_outside_repo` | `pass` | Overlay output directories are outside the repo. |
| `work_order_status_ready` | `pass` | Work-order status is contract_mapping_work_order_ready. |

## Assembled Rows

| Contract | Side | Selection | Probability | Executable Price | Timing |
| --- | --- | --- | ---: | ---: | --- |
| `KXNFLGAME-26SEP13ARILAC-ARI` | `yes` | `ARI` | 0.2081959141556554 | 0.19 | `pregame_clean` |
| `KXNFLGAME-26AUG06CARARI-ARI` | `yes` | `ARI` | 0.2081959141556554 | 0.5 | `pregame_clean` |
| `KXNFLGAME-26AUG13ARILV-ARI` | `yes` | `ARI` | 0.2081959141556554 | 0.72 | `pregame_clean` |
| `KXNFLGAME-26SEP13ARILAC-LAC` | `yes` | `LAC` | 0.7918040858443446 | 0.85 | `pregame_clean` |
| `KXNFLGAME-26SEP13ATLPIT-ATL` | `yes` | `ATL` | 0.3791767790633631 | 0.42 | `pregame_clean` |
| `KXNFLGAME-26SEP13ATLPIT-PIT` | `yes` | `PIT` | 0.6208232209366369 | 0.6 | `pregame_clean` |
| `KXNFLGAME-26SEP13BALIND-BAL` | `yes` | `BAL` | 0.5846634882495692 | 0.66 | `pregame_clean` |
| `KXNFLGAME-26SEP13BALIND-IND` | `yes` | `IND` | 0.4153365117504308 | 0.38 | `pregame_clean` |
| `KXNFLGAME-26SEP13BUFHOU-BUF` | `yes` | `BUF` | 0.4642920153598834 | 0.51 | `pregame_clean` |
| `KXNFLGAME-26SEP13BUFHOU-HOU` | `yes` | `HOU` | 0.5357079846401166 | 0.51 | `pregame_clean` |
| `KXNFLGAME-26SEP13CHICAR-CAR` | `yes` | `CAR` | 0.3983047217593665 | 0.44 | `pregame_clean` |
| `KXNFLGAME-26SEP13CHICAR-CHI` | `yes` | `CHI` | 0.6016952782406335 | 0.59 | `pregame_clean` |
| `KXNFLGAME-26SEP13CLEJAC-CLE` | `yes` | `CLE` | 0.2229654503545396 | 0.25 | `pregame_clean` |
| `KXNFLGAME-26SEP13CLEJAC-JAC` | `yes` | `JAX` | 0.7770345496454604 | 0.77 | `pregame_clean` |
| `KXNFLGAME-26SEP13DALNYG-NYG` | `yes` | `NYG` | 0.4310609964570717 | 0.43 | `pregame_clean` |
| `KXNFLGAME-26SEP14DENKC-DEN` | `yes` | `DEN` | 0.6383921331431862 | 0.46 | `pregame_clean` |
| `KXNFLGAME-26SEP14DENKC-KC` | `yes` | `KC` | 0.3616078668568138 | 0.6 | `pregame_clean` |
| `KXNFLGAME-26SEP13GBMIN-GB` | `yes` | `GB` | 0.3887168023031058 | 0.5 | `pregame_clean` |
| `KXNFLGAME-26SEP13GBMIN-MIN` | `yes` | `MIN` | 0.6112831976968942 | 0.53 | `pregame_clean` |
| `KXNFLGAME-26SEP13MIALV-LV` | `yes` | `LV` | 0.3537645476392154 | 0.64 | `pregame_clean` |
| `KXNFLGAME-26SEP13MIALV-MIA` | `yes` | `MIA` | 0.6462354523607845 | 0.38 | `pregame_clean` |
| `KXNFLGAME-26SEP09NESEA-NE` | `yes` | `NE` | 0.3083554472723144 | 0.37 | `pregame_clean` |
| `KXNFLGAME-26SEP09NESEA-SEA` | `yes` | `SEA` | 0.6916445527276855 | 0.66 | `pregame_clean` |
| `KXNFLGAME-26SEP13NODET-DET` | `yes` | `DET` | 0.7882220767047202 | 0.77 | `pregame_clean` |
| `KXNFLGAME-26SEP13NODET-NO` | `yes` | `NO` | 0.2117779232952797 | 0.25 | `pregame_clean` |
| `KXNFLGAME-26SEP13NYJTEN-NYJ` | `yes` | `NYJ` | 0.4835108350648447 | 0.45 | `pregame_clean` |
| `KXNFLGAME-26SEP10SFLAR-LAR` | `yes` | `LA` | 0.6499379233448707 | 0.65 | `pregame_clean` |
| `KXNFLGAME-26SEP10SFLAR-SF` | `yes` | `SF` | 0.3500620766551293 | 0.37 | `pregame_clean` |
| `KXNFLGAME-26SEP13TBCIN-CIN` | `yes` | `CIN` | 0.5342965389653818 | 0.65 | `pregame_clean` |
| `KXNFLGAME-26SEP13TBCIN-TB` | `yes` | `TB` | 0.4657034610346182 | 0.37 | `pregame_clean` |
| `KXNFLGAME-26SEP13WASPHI-PHI` | `yes` | `PHI` | 0.7389329793351639 | 0.67 | `pregame_clean` |
| `KXNFLGAME-26SEP13WASPHI-WAS` | `yes` | `WAS` | 0.2610670206648361 | 0.36 | `pregame_clean` |

## Next Action

Run make kalshi-ev-overlay-preflight && make kalshi-ev-ledger to evaluate the assembled overlay rows; execution remains disabled.
