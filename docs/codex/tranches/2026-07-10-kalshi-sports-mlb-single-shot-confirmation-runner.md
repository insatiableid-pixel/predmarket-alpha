# Tranche: MLB dense-panel immutable single-shot confirmation runner

Date: 2026-07-10
Branch: `codex/kalshi-sports-mlb-single-shot-confirmation-20260710T062445Z`
Base: `origin/main` @ `9b6642c` (merged PR #73)

## Purpose

Close the operational gap between a future `evidence_panel_ready` transition
and the frozen candidate's one permitted confirmation evaluation. The runner
must make continuous or accidental settlement peeking impossible.

## Frozen execution contract

- Contract version: `mlb_dense_panel_single_shot_confirmation_v1`
- Registered outcome-blind at: `2026-07-10T06:35:42Z`
- Contract hash:
  `306d226da9679b33011d44e31f239a1a57cc4ec27a9ef3eb90a9988265d403be`
- Original panel registration hash:
  `553135d7d1456aeda4a9115784aa423b81931cceed4d2a2f707b5ca8dcbe816e`
- Frozen candidate: `tight_spread_favorite_buy_yes_t60m`
- Formula hash:
  `9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d`
- Formula: T-60m, YES, `p_hat > 0.62`, `yes_spread <= 0.03`
- Implementation hashes are pinned in the contract and validated by preflight.

Contract artifacts:

- `docs/codex/macro/latest-kalshi-sports-mlb-dense-panel-confirmation-contract.json`
- `docs/codex/macro/latest-kalshi-sports-mlb-dense-panel-confirmation-contract.md`

## Lifecycle

1. `preflight` reads raw book evidence only. It never reads settlements.
2. It requires all registered panel gates plus:
   - at least 15 frozen-candidate events;
   - at least 8 contributing MLB slate dates;
   - largest candidate slate share no greater than 0.20;
   - candidate public-order-book share at least 0.95;
   - candidate executable-depth share at least 0.90;
   - every candidate decision strictly post-registration;
   - a 12-hour post-game settlement buffer;
   - valid raw, registration, contract, formula, and implementation hashes.
3. Only then is an exact sample written with exclusive create semantics to
   `single-shot-attempt.json`. The manifest contains no outcomes and may never
   expand.
4. Exact series-fee evidence is resolved before any settlement request. A fee
   fallback leaves the frozen attempt pending and outcome-blind.
5. Public Kalshi settlement truth is fetched only for frozen tickers. Missing
   settlements leave the same attempt pending; later events cannot enter.
6. Once complete, the runner performs one slate-clustered economic test and one
   slate-clustered calibration test, sets `p_joint=max(p_economic,p_calibration)`
   and the single-member `q_value=p_joint`, and applies the frozen bootstrap,
   temporal, breadth, source, depth, and fee gates.
7. The exclusive, self-hashed final sentinel is either
   `research_ready_survivor_research_only` or `confirmation_failed`. Replays
   return the same final artifact without network or inference calls.

Attempt and final sentinels are self-hashed. A tampered attempt is rejected
before fee or settlement access; a tampered final result is rejected rather
than replayed.

## Commands

```bash
make kalshi-sports-mlb-dense-panel-confirmation-contract
make kalshi-sports-mlb-dense-panel-confirmation-preflight
make kalshi-sports-mlb-dense-panel-confirmation-run
```

The contract command does not overwrite an existing contract without explicit
`--force`. The run command is safe while accumulating: it returns
`confirmation_pending_preflight_not_ready` without settlement access.

## Current real preflight

Generated at `2026-07-10T06:35:53Z`:

- status: `confirmation_pending`
- confirmation start ready: false
- candidate performance revealed: false
- candidate events / slates: 0 / 0
- raw rows: 30
- raw JSON integrity: pass; duplicate payload hashes: 0
- original registration hash: pass
- execution-contract hash: pass
- implementation hashes: pass
- attempt exists: false
- final exists: false
- settlement calls made by preflight: 0

Runtime state path:
`/home/mrwatson/manual_drops/kalshi_sports_mlb_dense_panel_confirmation/`

## Synthetic verification

- outcome-blind preflight reaches ready only at registered event/slate/breadth
  power;
- pending preflight makes zero settlement calls;
- uncertain fee evidence blocks before settlement calls;
- sample freezes once and cannot expand on resume;
- exact settlements can resume the same interrupted attempt;
- attempt tampering is rejected before settlement calls;
- a positive powered sample finalizes research-only and replays idempotently;
- a powered negative sample finalizes as `confirmation_failed`.

## Safety

Research-only. No threshold changes, v2 family, paper/live promotion, sizing,
accounts, credentials, approval queues, or orders. The dirty canonical checkout
and the active cron collector are untouched.
