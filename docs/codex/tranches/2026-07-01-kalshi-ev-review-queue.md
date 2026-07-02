# 2026-07-01 Kalshi EV Review Queue

## Summary

The command center now emits a ranked research-only Kalshi EV review queue. This moves the north-star workflow from "one usable row exists" to "all current mapped NFL contract rows are ranked, classified, and either queued or rejected with reasons."

Current queue status:

- Status: `kalshi_ev_review_queue_positive_candidates_need_robustness`
- Ledger rows: `348`
- Usable positive EV rows: `12`
- Positive watch rows: `5`
- Thin positive watch rows: `7`
- Robust candidates: `0`
- Rejected rows: `336`

The top row is:

```json
{
  "contract_ticker": "KXNFLGAME-26SEP13MIALV-MIA",
  "side": "yes",
  "selection": "MIA",
  "all_in_break_even_probability": 0.3965,
  "calibrated_probability": 0.6462354523607845,
  "margin_probability": 0.24973545236078448,
  "expected_roi": 0.629849816798952,
  "disposition": "positive_ev_watch"
}
```

This is not a bet recommendation, staking plan, execution instruction, or tradable claim.

## Implementation

- `scripts/kalshi_ev_review_queue.py`
  - Reads `docs/codex/macro/latest-kalshi-contract-ev-ledger.json`.
  - Queues only rows where `usable=true` and `margin_probability > 0`.
  - Ranks by robust disposition, margin, ROI, and contract ticker.
  - Classifies rows as `robust_positive_ev_review`, `positive_ev_watch`, or `thin_positive_ev_watch`.
  - Writes JSON, Markdown, and CSV outputs plus latest pointers.
- `scripts/kalshi_ev_nfl_overlay_assembler.py`
  - Deduplicates ready matches by `target_index + contract_ticker`.
  - Assembles the configurable unique work-order set, now `32` by default through `make`.
  - Keeps stable overlay filenames keyed by assembled contract set.
- `scripts/kalshi_contract_ev_ledger.py`
  - Deduplicates contract-mapping overlays by `source_repo_id + contract_ticker + side`.
- `scripts/codex_macro_router.py`
  - Reads the EV review queue as a first-class macro evidence surface.
  - Routes predmarket to the robustness-validation tranche when queued rows exist.

## Artifacts

- `docs/codex/macro/latest-kalshi-ev-review-queue.json`
- `docs/codex/macro/latest-kalshi-ev-review-queue.md`
- `docs/codex/macro/latest-kalshi-ev-review-queue.csv`
- `docs/codex/macro/latest-kalshi-contract-ev-ledger.json`
- `docs/codex/macro/latest-kalshi-ev-overlay-preflight.json`
- `docs/codex/macro/latest-kalshi-ev-nfl-overlay-assembler.json`
- `docs/codex/macro/latest-decision.json`

## Verification

- `make kalshi-ev-local-contract-evidence-scout`
- `make kalshi-ev-nfl-overlay-assembler`
- `make kalshi-ev-overlay-preflight`
- `make kalshi-ev-ledger`
- `make kalshi-ev-review-queue`
- `make macro-route`
- `make macro-unlock-scout`
- `make macro-blocker-audit`
- `make macro-status`
- Focused tests: `113 passed`
- Ruff on touched files: passed

## Next Tranche

The route now recommends robustness validation, not basic mapping:

> Inspect the ranked review queue, separate robust candidates from positive watch rows, and advance only robustness evidence such as repeat snapshots, actual ticket all-in cost confirmation, forward context, or independent validation.

Stop before treating queue rows as picks or touching execution/account/order paths.
