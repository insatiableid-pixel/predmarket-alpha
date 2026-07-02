# Kalshi EV Review Queue

- Status: `kalshi_ev_review_queue_positive_candidates_need_robustness`
- Research only: `true`
- Execution enabled: `false`
- Ledger rows: `348`
- Queued rows: `12`
- Robust candidates: `0`
- Positive watch rows: `5`
- Thin positive watch rows: `7`
- Robust margin threshold: `0.02`

## Queue

| Rank | Disposition | Contract | Selection | Break-even | Probability | Margin | ROI | Caveats |
| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `positive_ev_watch` | `KXNFLGAME-26SEP13MIALV-MIA` | `MIA` | 0.396500 | 0.646235 | 0.249735 | 0.629850 | fee is estimated from executable price |
| 2 | `positive_ev_watch` | `KXNFLGAME-26SEP14DENKC-DEN` | `DEN` | 0.477400 | 0.638392 | 0.160992 | 0.337227 | fee is estimated from executable price |
| 3 | `positive_ev_watch` | `KXNFLGAME-26SEP13TBCIN-TB` | `TB` | 0.386400 | 0.465703 | 0.079303 | 0.205237 | fee is estimated from executable price |
| 4 | `positive_ev_watch` | `KXNFLGAME-26SEP13GBMIN-MIN` | `MIN` | 0.547500 | 0.611283 | 0.063783 | 0.116499 | fee is estimated from executable price |
| 5 | `positive_ev_watch` | `KXNFLGAME-26SEP13WASPHI-PHI` | `PHI` | 0.685500 | 0.738933 | 0.053433 | 0.077947 | fee is estimated from executable price |
| 6 | `thin_positive_ev_watch` | `KXNFLGAME-26SEP13BALIND-IND` | `IND` | 0.396500 | 0.415337 | 0.018837 | 0.047507 | margin below robust review threshold 0.0200; fee is estimated from executable price |
| 7 | `thin_positive_ev_watch` | `KXNFLGAME-26SEP13NYJTEN-NYJ` | `NYJ` | 0.467400 | 0.483511 | 0.016111 | 0.034469 | margin below robust review threshold 0.0200; fee is estimated from executable price |
| 8 | `thin_positive_ev_watch` | `KXNFLGAME-26SEP09NESEA-SEA` | `SEA` | 0.675800 | 0.691645 | 0.015845 | 0.023446 | margin below robust review threshold 0.0200; fee is estimated from executable price |
| 9 | `thin_positive_ev_watch` | `KXNFLGAME-26SEP13BUFHOU-HOU` | `HOU` | 0.527500 | 0.535708 | 0.008208 | 0.015560 | margin below robust review threshold 0.0200; fee is estimated from executable price |
| 10 | `thin_positive_ev_watch` | `KXNFLGAME-26SEP13ARILAC-ARI` | `ARI` | 0.200800 | 0.208196 | 0.007396 | 0.036832 | margin below robust review threshold 0.0200; fee is estimated from executable price |
| 11 | `thin_positive_ev_watch` | `KXNFLGAME-26SEP13NODET-DET` | `DET` | 0.782400 | 0.788222 | 0.005822 | 0.007441 | margin below robust review threshold 0.0200; fee is estimated from executable price |
| 12 | `thin_positive_ev_watch` | `KXNFLGAME-26SEP13ATLPIT-PIT` | `PIT` | 0.616800 | 0.620823 | 0.004023 | 0.006523 | margin below robust review threshold 0.0200; fee is estimated from executable price |

## Next Action

Positive candidates exist, but current margins are thin or have robustness caveats. Next work: assemble the full available contract set, repeat snapshots, and require forward-context or independent validation before treating any row as stronger than watch-only research.
