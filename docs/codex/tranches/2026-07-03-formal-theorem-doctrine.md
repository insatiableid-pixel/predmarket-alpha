# Formal Theorem Doctrine

## Outcome

Landed the full Agentic Falsification Architecture theorem as the authoritative Codex runway doctrine. The formal theorem document at `docs/codex/macro/kalshi-agentic-falsification-architecture-theorem.md` supersedes the earlier condensed notes and is the single source of truth for the architecture's three axioms, two lemmas, the minimal construction theorem, the sequencing corollary, and the closing remark. The earlier `kalshi-agentic-falsification-architecture.md` and `kalshi-signal-factory-north-star.md` are explicitly noted as historical precursors. No executable code changed.

## Evidence

- `docs/codex/macro/kalshi-agentic-falsification-architecture-theorem.md` exists and reproduces the theorem faithfully: all three Axioms (No Discretion, Breadth Dominance, Capacity Boundedness with Pr[cap>0]~0.18 and $5K-$15K range), Lemma 1 (Kelly not Markowitz with the discrete-binary Kalshi remark), Lemma 2 (significance bar rises in K with agentic-generation remark), Theorem (formal argmax + feasibility + minimality proofs), Corollary (sequencing: sports first), and Closing Remark (operator is the object of value).
- `docs/codex/current-state.md` prepended with the theorem-doctrine landing entry; `Last updated` refreshed to 2026-07-03.
- Mission scope boundary explicitly stated: Kelly sizing layer blocked in this mission (research-only; usable=false throughout).
- `make test-unit` and `make validate-agents` continue to pass (no code changed).

## Learned

- The formal theorem had existed in condensed form in `library/falsification-theorem.md` but had not been published as a standalone formal document in the Codex runway. The library version served as the source of truth for the math; the new document expands each component with formal notation, proof sketches, operational consequences, and explicit mission-scope boundaries.
- The earlier `kalshi-agentic-falsification-architecture.md` (a shorter architectural note) and `kalshi-signal-factory-north-star.md` (a north-star statement) both referenced parts of the theorem but were not the full formal version. The new document supersedes both.

## Next Route

Cross-family integration finalization: run the full multi-family watch-once chain across all 3 families, verify global research-only safety, confirm Codex runway consistency, run binding quality gates, and update the README.

## Guardrail

This is a DOCTRINE/DOCS feature — no executable code was created or modified. The theorem's mission-scope boundary is explicit: the Kelly sizing layer is blocked. Every artifact in this mission remains `usable=false`, `research_only=true`, `execution_enabled=false`. No execution, account, order, or DB-write paths.
