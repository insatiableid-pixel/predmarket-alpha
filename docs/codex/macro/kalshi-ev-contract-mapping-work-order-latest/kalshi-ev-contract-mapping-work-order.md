# Kalshi EV Contract Mapping Work Order

- Status: `contract_mapping_work_order_ready`
- Research only: `true`
- Source repo: `nfl_quant_glm51_greenfield`
- Model rows: `16`
- Selected contract sides: `32`
- Validation artifacts: `2`

## Selected NFL Rows

| Game | Selection | Probability | Market Reference | Delta | Calibration | Required Next Fact |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `MIA@LV` | `LV` | 0.3537645476392154 | 0.6183206106870229 | -0.26455606304780754 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `MIA@LV` | `MIA` | 0.6462354523607845 | 0.38167938931297707 | 0.26455606304780743 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `DEN@KC` | `DEN` | 0.6383921331431862 | 0.4314881077667859 | 0.2069040253764003 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `DEN@KC` | `KC` | 0.3616078668568138 | 0.5685118922332141 | -0.2069040253764003 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `GB@MIN` | `GB` | 0.3887168023031058 | 0.5149751839808319 | -0.12625838167772607 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `GB@MIN` | `MIN` | 0.6112831976968942 | 0.4850248160191682 | 0.12625838167772602 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `TB@CIN` | `CIN` | 0.5342965389653818 | 0.6369041816941223 | -0.10260764272874057 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `TB@CIN` | `TB` | 0.4657034610346182 | 0.36309581830587767 | 0.10260764272874051 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `WAS@PHI` | `PHI` | 0.7389329793351639 | 0.6564885496183206 | 0.08244442971684329 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `WAS@PHI` | `WAS` | 0.2610670206648361 | 0.3435114503816794 | -0.08244442971684329 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `NYJ@TEN` | `NYJ` | 0.4835108350648447 | 0.4201680672268908 | 0.0633427678379539 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `NYJ@TEN` | `TEN` | 0.5164891649351553 | 0.5798319327731092 | -0.0633427678379539 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `BAL@IND` | `BAL` | 0.5846634882495692 | 0.635775996022127 | -0.051112507772557825 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `BAL@IND` | `IND` | 0.4153365117504308 | 0.364224003977873 | 0.05111250777255777 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `NE@SEA` | `NE` | 0.3083554472723144 | 0.35876814909344834 | -0.05041270182113394 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `NE@SEA` | `SEA` | 0.6916445527276855 | 0.6412318509065517 | 0.05041270182113389 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `NO@DET` | `NO` | 0.2117779232952797 | 0.25912838633686697 | -0.04735046304158727 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `NO@DET` | `DET` | 0.7882220767047202 | 0.740871613663133 | 0.04735046304158719 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `BUF@HOU` | `BUF` | 0.4642920153598834 | 0.5108342361863489 | -0.04654222082646553 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `BUF@HOU` | `HOU` | 0.5357079846401166 | 0.4891657638136511 | 0.046542220826465475 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `CHI@CAR` | `CAR` | 0.3983047217593665 | 0.4424778761061947 | -0.044173154346828225 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `CHI@CAR` | `CHI` | 0.6016952782406335 | 0.5575221238938053 | 0.044173154346828225 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `ARI@LAC` | `LAC` | 0.7918040858443446 | 0.827123695976155 | -0.0353196101318104 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `ARI@LAC` | `ARI` | 0.2081959141556554 | 0.17287630402384502 | 0.03531961013181037 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `ATL@PIT` | `ATL` | 0.3791767790633631 | 0.40997934212617193 | -0.03080256306280882 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `ATL@PIT` | `PIT` | 0.6208232209366369 | 0.5900206578738281 | 0.03080256306280882 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `SF@LA` | `SF` | 0.3500620766551293 | 0.37889039242219213 | -0.02882831576706285 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `SF@LA` | `LA` | 0.6499379233448707 | 0.6211096075778079 | 0.028828315767062795 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `CLE@JAX` | `CLE` | 0.2229654503545396 | 0.24725865405289182 | -0.024293203698352223 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `CLE@JAX` | `JAX` | 0.7770345496454604 | 0.7527413459471082 | 0.024293203698352195 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `DAL@NYG` | `NYG` | 0.4310609964570717 | 0.449717730360731 | -0.018656733903659295 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |
| `DAL@NYG` | `DAL` | 0.5689390035429283 | 0.5502822696392691 | 0.018656733903659184 | `platt_logit` | exact Kalshi ticker + official terms + executable cost |

## Templates

- Contract mapping template: `docs/codex/macro/latest-kalshi-ev-contract-mapping-template.json`
- Matching probability template: `docs/codex/macro/latest-kalshi-ev-contract-mapped-probability-template.json`

Both templates are marked `template_only=true` and use TODO statuses so they are not evidence. Filled overlays belong under `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/` and `/home/mrwatson/manual_drops/kalshi_ev_probabilities/`.

## Next Action

Fill exact Kalshi ticker, official terms, clean timing status, and executable cost for one selected NFL row; write matching contract-mapping and calibrated-probability overlays under /home/mrwatson/manual_drops/kalshi_ev_contract_mappings/ and /home/mrwatson/manual_drops/kalshi_ev_probabilities/, then rerun overlay preflight and the EV ledger.
