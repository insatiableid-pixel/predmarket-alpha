# 2026-06-30 MLB Settled-Validation Command Center Refresh

The macro command center now recognizes MLB's settled-outcome validation.

MLB status advanced from `primary_type2_threshold_policy_hold_current` to
`primary_type2_settled_validation_no_policy_change_same_slate`.

The routed truth is:

- settled-validation status: `settled_validation_no_policy_change_same_slate`
- settled directional rows: 1,239
- directional correctness: 45.0%
- current threshold candidates: 0
- slate dates represented: 1

Plain English: settled outcomes do not support lowering thresholds. The next
useful input is an independent clean slate or closing-line validation.

Updated surfaces:

- `scripts/codex_macro_router.py`
- `scripts/codex_macro_unlock_scout.py`
- `docs/codex/macro/latest-status.json`
- `docs/codex/macro/latest-decision.json`
- `docs/codex/macro/latest-decision.md`
- `docs/codex/macro/latest-unlock-scout.json`
- `docs/codex/macro/latest-unlock-scout.md`

`make macro-route` parks all lanes and recommends predmarket as command center
for blocker collection. No execution, account/order path, provider/API call,
database write, threshold lowering, or tradable claim is authorized.
