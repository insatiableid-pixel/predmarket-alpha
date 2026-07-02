# AGENTS.md

## Project Root

Canonical path:

```text
/home/mrwatson/projects/predmarket-alpha
```

This is the active prediction-market research platform root.

## North Star

Extract and exploit mispricings in Kalshi event contracts before the crowd
corrects them.

Build a self-improving, systematic, purely quantitative operation that finds
non-random probability decay in Kalshi crowd-implied prices, falsifies candidate
signals out of sample, converts surviving signals into calibrated probabilities,
and only then advances toward capacity-aware sizing and execution controls.

Operating axioms:

- No discretion: humans configure systems; machines select, size, enter, exit,
  retire, and replace signals.
- Signal breadth over depth: scale comes from many weak, uncorrelated signals
  across many markets, not concentrated conviction.
- Capacity discipline is structural: Kalshi edge scales through market count
  because liquidity and price impact cap useful position size.

## Codex Runway

- Read `docs/codex/current-state.md` before starting long-running work.
- Add compact handoff notes under `docs/codex/tranches/`.
- Use `/goal` for longer autonomous Kalshi research-desk improvement runs.
- Cleanup, failed verification, stale processes, and landing residue come before
  new feature work.

## Environment

- Use the local venv at `.venv/`.
- Prefer Make targets over ad hoc command strings.
- Keep generated runtime artifacts under existing ignored runtime/output paths.

## Common Commands

```bash
make check-env
make test
make lint
make kalshi-verify
make kalshi-smoke
make kalshi-rank
make kalshi-cycle
make kalshi-ledger
```

Use focused tests for touched `predmarket/kalshi_*` modules and run the full
suite when touching shared store, CLI, or execution-adjacent code.

## Research-Only Guardrails

- Kalshi work is research-only unless the user explicitly asks for execution.
- Do not touch live execution or approval queues while improving paper research
  loops.
- Keep promotion-readiness gates hard and non-overridable unless a tranche
  explicitly changes the contract.
- Prefer replayable saved artifacts over live-only state.
