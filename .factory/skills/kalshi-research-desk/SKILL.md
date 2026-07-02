---
name: kalshi-research-desk
description: Run the Kalshi signal-factory research desk loop (universe scan, hypothesis registry, labeled OOS backtest, crypto proxy observation loop). Use when starting or resuming Kalshi research-only work.
---

# Kalshi Research Desk Skill

## Purpose

Operate the Kalshi signal-factory research desk in research-only mode. This skill
guides the full safe chain: universe scanning, hypothesis falsification, labeled
OOS backtesting, crypto proxy feature/observation/model/replay, and capacity/
correlation/decay gating.

## Critical Guardrails

- All work is **research-only** unless the user explicitly asks for execution.
- Never touch live execution or approval queues.
- Every artifact row must remain `usable=false`, `research_only=true`.
- Keep promotion-readiness gates hard and non-overridable.
- Prefer replayable saved artifacts over live-only state.

## Standard Workflow

1. Read `docs/codex/current-state.md` and `docs/codex/macro/latest-decision.md`.
2. Run `make macro-route` to confirm the routed tranche.
3. Execute the routed target (e.g., `make kalshi-crypto-proxy-observation-watch-once`).
4. Run `make kalshi-signal-factory-status` to refresh the status.
5. Run `make macro-route` to update the decision.
6. Write a tranche note under `docs/codex/tranches/`.
7. Update `docs/codex/current-state.md`.

## Verification

```bash
make check-env
make kalshi-verify
make lint-baseline-check
make test-unit
```
