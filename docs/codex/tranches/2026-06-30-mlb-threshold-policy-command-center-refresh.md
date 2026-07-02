# 2026-06-30 MLB Threshold-Policy Command Center Refresh

The macro command center now recognizes MLB's threshold-policy review.

MLB status advanced from `primary_type2_repeatability_no_signal_clean_packets`
to `primary_type2_threshold_policy_hold_current`.

The routed truth is:

- threshold-policy status: `threshold_policy_hold_current`
- current threshold candidates: 0
- max absolute net difference: 0.0277
- slate dates represented: 1
- best lower-threshold candidate: 0.0200

Plain English: the review says the threshold should stay where it is. The
next useful input is not more same-slate coding; it is an independent clean
slate or settled/closing-line validation.

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
