# Overdue Fable Sports Evidence Probes

Date: 2026-07-08

## Summary

Resumed the Fable sports evidence loop after several overdue blocker clocks and ran the settlement/probe sequence through the existing gates. The canonical shared `.venv` has a broken `python3.14` symlink, so the due runs used a disposable pinned runtime at `/tmp/predmarket-alpha-fable-venv` with `VENV=/tmp/predmarket-alpha-fable-venv`. No repo code changed for that environment repair.

## Evidence State

- Fable audit: `15/15` implementation, `10/15` evidence.
- Open ids: `CLAUDE-005`, `CLAUDE-008`, `CLAUDE-012`, `CLAUDE-014`, `CLAUDE-015`.
- Sports consensus falsification: `964` joined labels, `70` independent labels, `21` OOS labels, `1` tested hypothesis, `0` FDR survivors.
- ATP evidence gate: settled labels advanced from `842` to `962`, but forward-OOS remains `8/10`; next expected expiration is `2026-07-09T06:00:00Z`.
- Paper: `0` usable rows and `$0` stake.
- Live: `0` eligible rows and `$0` stake.
- Next blocker clock: `2026-07-08T17:35:00Z`.

## Remaining Blockers

- `CLAUDE-005`: ATP forward-OOS still `8/10`.
- `CLAUDE-008`: sports-event velocity still has `total_label_deficit=96` and `total_oos_deficit=35`.
- `CLAUDE-012`: Kalshi tick recorder still blocked by invalid RSA private-key material.
- `CLAUDE-014`: historical sharp-consensus backfill still blocked by paid/archive access.
- `CLAUDE-015`: soccer provider coverage still missing `ibc`, `sbobet`, and `singbet`.

## Guardrails

No thresholds changed. No labels were inferred. No sportsbook results were used as settlement labels. No EV, paper, live, account, order, or execution promotion occurred.

## Verification

- `make kalshi-sports-blocker-clearance-cycle KALSHI_SPORTS_BLOCKER_CLEARANCE_RUN_DUE=1 VENV=/tmp/predmarket-alpha-fable-venv`
- `make kalshi-sports-event-velocity-eta VENV=/tmp/predmarket-alpha-fable-venv`
- `make kalshi-claude-advice-audit VENV=/tmp/predmarket-alpha-fable-venv`
- `make kalshi-sports-blocker-clearance-cycle VENV=/tmp/predmarket-alpha-fable-venv`

All commands exited `0` after the disposable venv was created from pinned `requirements.txt`.
