# 2026-07-03 Family-Aware Orchestration

## Outcome

Generalized the three single-family orchestration scripts so the factory reports
and routes MULTIPLE signal families (crypto_proxy + sports_baseball) without being
hardcoded to crypto. All changes are ADDITIVE: crypto behavior and its 143
characterization tests stay green (strangler-fig precursor).

## Evidence

- `scripts/kalshi_signal_factory_status.py` (1427 lines) + companion
  `scripts/kalshi_signal_factory_families.py` (245 lines): the status report now
  iterates a family registry, emitting per-family capability groupings
  (`report["families"]["crypto_proxy"]` and `report["families"]["sports_baseball"]`)
  plus a multi-family summary rollup (`report["summary"]["families"]`). The
  `Artifacts` dataclass carries family-keyed sports paths (crypto defaults
  preserved). Top-level status is selected across families by advancement rank
  with a documented `status_selection` note.
- `scripts/kalshi_probability_breadth_scout.py` (760 lines): added
  `sports_baseball_fast_label_route` for KXMLBGAME/KXKBOGAME/KXLMBGAME series
  classification. Sports candidates are NOT shadowed or starved by crypto; both
  surface when both present (order-independent). Summary now carries
  `sports_fast_candidate_count`. Weather route preserved.
- `scripts/codex_macro_router.py` (6757 lines, additive only): every
  `signal_factory_sports_*` status is in `apply_scheduling()` priority-override
  set (priority >= 0, tier parity with crypto), has a sports-specific tranche +
  stop condition, and has a `PARKED_UNLOCKS` entry. Sports artifact paths added
  to `predmarket_status()`.

## Learned

- The family registry pattern (companion module with `family_status_rank()` +
  per-family builders) lets adding a family be a data change rather than a
  rewrite of the capability-construction code path. The rank-based top-level
  status selection is deterministic, documented, and preserves crypto behavior
  (ties go to crypto).
- Sports classification must check the series ticker directly
  (KXMLBGAME/KXKBOGAME/KXLMBGAME) because `classify_market()` only recognizes
  MLB-prefix tickers, not KBO/LMB. The sports predicate explicitly excludes
  run-line (KXMLBRUN) and player-prop (KXMLBPLAYER) variants.
- The 1500-line file-size ratchet forced extracting the family registry into a
  companion module, which actually improved the design (single responsibility).

## Next Route

The sports feature-packet builder (`sports-feature-packet`) and observation/label
loop (`sports-observation-label-loop`) are the next M1 features. They will produce
the `latest-kalshi-sports-proxy-feature-packet.json` and
`latest-kalshi-sports-proxy-observation-loop.json` artifacts that this
orchestration layer is already wired to consume.

## Guardrail

Every artifact remains research-only: `usable=false`, `calibrated_probability=null`,
`research_only=true`, `execution_enabled=false`. No execution, account/order, or
database-write paths. The sports source plan names official game results as the
settlement source and MLB Stats API / ESPN as proxy model features only.
