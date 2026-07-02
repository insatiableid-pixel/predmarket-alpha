# MLB Review Adjudication Router Refresh

Date: 2026-06-29

## Summary

Updated the macro command center after MLB completed its clean same-slate pregame review adjudication.

## What Changed

- `scripts/codex_macro_router.py` now recognizes MLB `review-adjudication.json` artifacts.
- MLB macro status can report `primary_type2_review_adjudication_ready`.
- The MLB recommended tranche changed from first-pass review adjudication to a repeatability ledger.
- `scripts/codex_macro_unlock_scout.py` now describes the MLB missing input as a second clean same-slate pregame pair for stability comparison.
- `docs/codex/current-state.md` and `docs/codex/macro/federated-market-edge-os-plan.md` now reflect the new state.

## Current MLB Truth

- Clean pregame pair: ready.
- Review adjudication: ready.
- Review-ready rows: 58.
- Review-ready clusters: 8.
- Adjudication gates: all pass.
- Next blocker: another clean pregame pair to test repeatability.

## Guardrails

No provider calls, database writes, market execution, account/order paths, or tradable claims were added by this command-center refresh.
