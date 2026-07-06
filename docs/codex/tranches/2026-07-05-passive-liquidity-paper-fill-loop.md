# Passive-Liquidity Paper Fill Loop

Date: 2026-07-05

## Purpose

Continue implementing Claude's sports advice by starting the passive-liquidity maker evidence clock. The prior passive-liquidity gate was honest but incomplete: it emitted counterfactual public-orderbook touch proxies and then blocked because proxy labels are not real fill evidence.

This tranche adds a paper maker-intent loop that persists quote intents and labels only prior intents from later public snapshots. It remains research-only and does not claim real Kalshi exchange fills.

## Landing

- Added `scripts/kalshi_passive_liquidity_paper_fill_loop.py`.
- Added `make kalshi-passive-liquidity-paper-fill-loop`.
- Wired the new target into `make kalshi-sports-nondirectional-evidence-watch-once` after the passive-liquidity proxy gate.
- Added `latest-kalshi-passive-liquidity-paper-fill-loop.{json,md}` plus intent/label CSV latest pointers under `docs/codex/macro/`.
- Persisted state outside the repo under `/home/mrwatson/manual_drops/kalshi_passive_liquidity_paper_fills/`.
- Updated `scripts/kalshi_sports_evidence_cycle_report.py` so sports cycle reports passive paper intent/open/label counts as a separate 25th safe artifact.
- Added focused tests in `tests/test_kalshi_passive_liquidity_paper_fill_loop.py`.

## Guardrails

- New intents created in a run are never labeled in that same run.
- Labels are only `paper_filled_from_later_public_touch` or `paper_expired_unfilled_no_public_touch`.
- `real_exchange_fill_label_count` remains `0`.
- No account, order, market execution, probability, EV, or sizing path is touched.
- Temp output directories do not mutate global macro latest pointers.

## Real Run

`make kalshi-sports-nondirectional-evidence-watch-once` exits 0.

Current artifacts:

- Microstructure rows: `3022`
- Forward quote labels: `881`
- Passive counterfactual proxy labels: `164`
- Passive would-touch proxies: `7`
- Passive paper intents: `0`
- Passive paper fill labels: `0`
- Near-resolution flow replay: `near_resolution_flow_replay_gates_blocked_capacity_depth`
- Passive paper-fill status: `passive_liquidity_paper_fill_loop_blocked_no_paper_intents`

Reason for zero paper intents: the current 120-row near-resolution sports sample has no two-sided books and no one-sided ask above `1c` that can support a conservative passive bid. The loop is ready; the market sample did not offer a defensible paper maker intent.

## Verification

- `python -m pytest -s -q tests/test_kalshi_passive_liquidity_paper_fill_loop.py tests/test_kalshi_sports_evidence_cycle_report.py` -> `6 passed`
- `python -m ruff check` on touched script/test files -> clean
- `python -m py_compile` on touched scripts -> clean
- `make kalshi-sports-nondirectional-evidence-watch-once` -> exits 0
- `make kalshi-sports-evidence-cycle-report` -> exits 0, `25/25` safe artifacts

## Claude Implementation Estimate

- Sports sharp-consensus wrapping: `80%` by target sport count (`4/5`).
- Mature sharp-provider coverage: `60%` (`3/5`).
- Near-resolution informed-flow plumbing: ~`90%`, but current replay is capacity/depth blocked.
- Passive liquidity: ~`55%`; stateful paper-intent/label loop exists, but current market sample has no intents/labels and there is not yet a passive paper-fill FDR ledger.
- Overall Claude advice set: roughly `75%` implemented.

Remaining work is concentrated in label accumulation, NBA strict consensus, soccer Asian-sharp enrichment, passive paper fill labels plus FDR, capacity/depth unblock, and paper promotion only after gates pass.
