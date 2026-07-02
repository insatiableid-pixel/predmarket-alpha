# Kalshi EV Local Contract Evidence Scout

- Status: `local_contract_evidence_ready_for_overlay_fill`
- Research only: `true`
- Local JSON files: `12`
- Contract evidence rows: `10740`
- NFL contract evidence rows: `164`
- Target contract sides: `32`
- Possible target matches: `172`
- Ready target matches: `172`

## Gates

| Gate | Status | Reason |
| --- | --- | --- |
| `research_only_no_live_calls` | `pass` | Scout reads local JSON files only; live/provider calls are not implemented. |
| `local_json_files_present` | `pass` | Found 12 local JSON file(s) in configured search paths. |
| `contract_evidence_rows_present` | `pass` | Extracted 10740 local Kalshi-like contract row(s). |
| `target_work_order_rows_present` | `pass` | Loaded 32 target contract side(s) from the mapping work order. |
| `nfl_contract_snapshot_present` | `pass` | Found 164 local NFL contract evidence row(s). |
| `possible_target_match_present` | `pass` | Found 172 possible target match(es). |
| `ready_target_contract_evidence_present` | `pass` | Found 172 target match(es) with ticker, terms, and executable cost. |
| `clean_timing_evidence_present` | `pass` | At least one target match includes clean timing evidence. |

## Target Matches

| Game | Selection | Contract | Quality | Ask | Source |
| --- | --- | --- | --- | ---: | --- |
| `ARI@LAC` | `ARI` | `KXNFLGAME-26SEP13ARILAC-ARI` | `ready_exact_local_evidence` | 0.19 | `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260701T185756Z.json` |
| `ARI@LAC` | `ARI` | `KXNFLGAME-26SEP13ARILAC-ARI` | `ready_exact_local_evidence` | 0.19 | `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json` |
| `ARI@LAC` | `ARI` | `KXNFLGAME-26AUG06CARARI-ARI` | `ready_exact_local_evidence` | 0.5 | `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json` |
| `ARI@LAC` | `ARI` | `KXNFLGAME-26AUG13ARILV-ARI` | `ready_exact_local_evidence` | 0.72 | `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json` |
| `ARI@LAC` | `ARI` | `KXNFLGAME-26SEP13ARILAC-ARI` | `ready_exact_local_evidence` | 0.19 | `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json` |
| `ARI@LAC` | `LAC` | `KXNFLGAME-26SEP13ARILAC-LAC` | `ready_exact_local_evidence` | 0.85 | `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260701T185756Z.json` |
| `ARI@LAC` | `LAC` | `KXNFLGAME-26SEP13ARILAC-LAC` | `ready_exact_local_evidence` | 0.85 | `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json` |
| `ARI@LAC` | `LAC` | `KXNFLGAME-26SEP13ARILAC-LAC` | `ready_exact_local_evidence` | 0.85 | `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json` |
| `ATL@PIT` | `ATL` | `KXNFLGAME-26SEP13ATLPIT-ATL` | `ready_exact_local_evidence` | 0.42 | `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260701T185756Z.json` |
| `ATL@PIT` | `ATL` | `KXNFLGAME-26SEP13ATLPIT-ATL` | `ready_exact_local_evidence` | 0.42 | `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json` |
| `ATL@PIT` | `ATL` | `KXNFLGAME-26SEP13ATLPIT-ATL` | `ready_exact_local_evidence` | 0.42 | `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json` |
| `ATL@PIT` | `PIT` | `KXNFLGAME-26SEP13ATLPIT-PIT` | `ready_exact_local_evidence` | 0.6 | `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260701T185756Z.json` |
| `ATL@PIT` | `PIT` | `KXNFLGAME-26SEP13ATLPIT-PIT` | `ready_exact_local_evidence` | 0.6 | `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json` |
| `ATL@PIT` | `PIT` | `KXNFLGAME-26SEP13ATLPIT-PIT` | `ready_exact_local_evidence` | 0.6 | `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json` |
| `BAL@IND` | `BAL` | `KXNFLGAME-26SEP13BALIND-BAL` | `ready_exact_local_evidence` | 0.66 | `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260701T185756Z.json` |
| `BAL@IND` | `BAL` | `KXNFLGAME-26SEP13BALIND-BAL` | `ready_exact_local_evidence` | 0.66 | `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json` |
| `BAL@IND` | `BAL` | `KXNFLGAME-26SEP13BALIND-BAL` | `ready_exact_local_evidence` | 0.66 | `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json` |
| `BAL@IND` | `IND` | `KXNFLGAME-26SEP13BALIND-IND` | `ready_exact_local_evidence` | 0.38 | `/home/mrwatson/manual_drops/kalshi/kalshi_mlb_game_series_20260701T185756Z.json` |
| `BAL@IND` | `IND` | `KXNFLGAME-26SEP13BALIND-IND` | `ready_exact_local_evidence` | 0.38 | `/home/mrwatson/manual_drops/kalshi/kalshi_nfl_game_series_latest.json` |
| `BAL@IND` | `IND` | `KXNFLGAME-26SEP13BALIND-IND` | `ready_exact_local_evidence` | 0.38 | `/home/mrwatson/manual_drops/kalshi_ev_contract_mappings/kalshi_ev_nfl_contract_mapping_overlay_keys_96008378d65c.json` |

## Next Action

Use one ready target match to fill safe contract-mapping and calibrated-probability overlays outside the repo, then run make kalshi-ev-overlay-preflight && make kalshi-ev-ledger.
