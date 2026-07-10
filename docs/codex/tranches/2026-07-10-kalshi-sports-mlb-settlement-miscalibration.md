# Tranche: Fixed-clock MLB settlement-miscalibration factory

Date: 2026-07-10
Branch: codex/kalshi-sports-mlb-miscalibration-20260710T050210Z
Base: origin/main @ e2e3d3c (verified ancestors e2e3d3c, 87a62d6, 9742ee5)
Directive: GROK_KALSHI_SPORTS_MLB_MISCALIBRATION_DIRECTIVE_20260710T045953Z

## Actions

- Left dirty canonical checkout untouched; clean collision-safe worktree/branch from refreshed origin/main.
- Phase 0 novelty map vs negative registry; timestamp/as-of join audit; synthetic leakage/fee suite (7/7 pass).
- Phase 1 fixed pregame clocks T-24h/T-6h/T-60m/T-15m with frozen staleness; dense MLB book capture helper.
- Phase 2 calibration residual surface vs hold-to-settlement economics (ask + single entry fee; no exit fee).
- Phase 3 finite registry (11 specs); baselines only as controls; novel path/clock/listing mechanisms.
- Phase 4 event-grouped walk-forward + complete-family FDR; orderbook-only promotion economics.
- Phase 5 confirmation ledger frozen; no post-cutoff confirmation sample available.
- **Outcome B**: family falsified at pre-registered power; 0 research-ready survivors.

## Evidence

- Status: `mlb_settlement_miscalibration_family_falsified`
- Labeled rows: 1168; distinct events: 175; max clock events: 169
- FDR survivors: 0; research-ready: 0
- Near-misses retired for `cluster_share_le_0_35` after FDR pass:
  - `path_slope_continuation_buy_yes_t60m` oos=21 mean_net≈0.147 q≈2.86e-6
  - `tight_spread_favorite_buy_yes_t60m` oos=20 mean_net≈0.095 q≈2.86e-6
- Latest: `docs/codex/macro/latest-kalshi-sports-mlb-settlement-miscalibration.json`
- Negative registry + frontier updated (prior short-horizon falsifications preserved)

## Verification

- `pytest tests/test_kalshi_sports_mlb_settlement_miscalibration.py` → 6 passed
- Ruff clean on touched modules/scripts/tests

## Guardrails

- Research-only: no paper stake, sizing, accounts, orders, or live execution
- No cosmetic retune of retired v1 thresholds
- Next distinct surface: multi-week dense fixed-clock orderbook panel v2

