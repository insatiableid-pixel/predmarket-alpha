# Kalshi Sports Max-Leverage Final Audit

Directive: `kalshi-sports-max-leverage-20260710T043157Z`  
Generated from worktree branch `codex/kalshi-sports-max-leverage-20260710T043635Z`  
Primary latest entry point: `docs/codex/macro/latest-kalshi-sports-executable-horizon-research.{json,md,csv}`

## Decision

**No research-ready survivor.** Outcome closer to **Outcome B** for the declared
high-leverage families that can be tested with currently available legal Kalshi
sports microstructure snapshots:

| Family | Status | Evidence |
| --- | --- | --- |
| Prior historical multi-book MLB consensus | falsified (prior) | 1,098 labels, 0 FDR survivors |
| Prior near-resolution simple flow (mid forward) | falsified (prior) | best q ~ 0.999 |
| Prior passive-liquidity paper fills | falsified (prior) | best q = 1.0, best net EV ~ -0.0183 |
| Prior settlement-direction flow | confirmation_failed (prior) | 8/18 paper correct, cal err ~ 0.53 |
| `sports_executable_horizon_microstructure_v1` | **falsified** | 3,584 executable labels; 7 testable; 0 FDR survivors; all mean net < 0 |
| `sports_cross_contract_leadlag_v1` | **falsified** | 4 testable; 0 FDR survivors; all mean net < 0 |
| `sports_thin_book_fade_v1` | **falsified** | 2 testable; 0 FDR survivors; all mean net < 0 |

**Research-ready survivor exists:** no  
**Paper stake / sizing / accounts / orders / live execution activated:** no

## What was built (Phases 0–3)

1. **Phase 0 truth/leakage audit** — inventory of 11,061 unique sports
   microstructure observations (2,227 contracts, 525 events), frozen checksum
   reconciliation (4/4), documented prior label-semantic defects (fake 60/300/900
   mid deltas; midpoint-not-executable promotion risk), synthetic leakage suite
   pass.
2. **Phase 1 executable labels** — aggressive entry at ask / exit at future bid,
   general taker fees both legs, explicit censoring for missing/gap horizons,
   diagnostic mid delta only. Horizons 60/300/900s with tolerances.
3. **Phase 2 finite registries** — 26 pre-registered candidates across three
   distinct families including negative controls; FDR over complete families.
4. **Phase 3 event-grouped walk-forward** — event-collapsed independence,
   chronological folds with embargo, cluster bootstrap lower bound, temporal
   buckets, capacity and series-share gates.

Untouched confirmation cutoff declared at generation time; discovery used only
pre-cutoff snapshots. No candidate reached FDR survival, so confirmation was not
armed.

## Exact economics (discovery OOS)

Across all testable candidates, **mean executable net return after fees/spread
was negative**. Best (least bad) observed mean net among insufficient-sample
rows was about `-0.0198` per contract
(`tight_spread_imbalance_buy_yes_h900`, 52 OOS events). All q-values for
testable candidates were `1.0` under complete-family BH-FDR at alpha `0.05`.

This is consistent with a structural cost floor: buy-ask / sell-bid round trips
plus taker fees dominate the short-horizon mid moves available at the current
snapshot cadence (median inter-observation gap ~27 minutes; true 60s labels
mostly censored).

## Label surface quality

- Observation rows: **11,061**
- Label rows (3 horizons): **33,183**
- Executable labeled: **3,584**
- Censored (no future / horizon gap): **29,119**
- Blocked invalid books: **480**
- Surfaces: MLB-heavy (`mlb` 7,972), world cup soccer, ATP

## Gates preserved

- Exact provenance + source hashes on labels
- Event-grouped independence and embargoed folds
- Complete-family FDR (not post-hoc subset)
- After-cost executable returns (not accuracy-only)
- Temporal buckets, capacity, largest series share ≤ 0.35 gate definitions
- Research-only flags: `usable_row_count=0`, `paper_stake=0`, `live_eligible=0`
- No gate weakened after seeing results

## Remaining ranked queue (not promotion candidates)

1. **Dense MLB tick/orderbook capture** — infrastructure to unlock true 1–5
   minute executable labels (current ticks: 2 small JSONL files). This is a new
   data surface, not a re-tune of falsified specs.
2. **ATP forward OOS / settlement velocity** — calendar monitors only.
3. **Asian-sharp soccer** — explicitly deferred / out of scope.

## Outcome classification

- **Outcome A:** not met.
- **Outcome B (declared testable families):** met for the three newly declared
  executable-horizon families plus the prior negative registry. Remaining queue
  items are either infrastructure (dense ticks), calendar-bound, or authority-
  deferred — not untested high-leverage signal families on the same label design.

If denser ticks arrive, register a **new** finite family against the new label
surface; do not resurrect the retired model_ids above.

## Verification

- Focused tests: `pytest tests/test_kalshi_sports_executable_horizon.py` → 6 passed
- `make kalshi-sports-executable-horizon-research` →
  `executable_horizon_research_family_falsified`
- Ruff clean on touched modules/scripts
- Frozen starting evidence checksums reconciled (see Phase 0 audit JSON)

## Entry points

| Surface | Path |
| --- | --- |
| Program latest | `docs/codex/macro/latest-kalshi-sports-executable-horizon-research.json` |
| Frontier | `docs/codex/macro/latest-kalshi-sports-research-frontier.json` |
| Negative registry | `docs/codex/macro/latest-kalshi-sports-negative-result-registry.json` |
| Truth/leakage audit | `docs/codex/macro/latest-kalshi-sports-truth-leakage-audit.json` |
| Hypothesis registry | `docs/codex/macro/latest-kalshi-sports-executable-hypothesis-registry.json` |
| Label export (ignored) | `/home/mrwatson/manual_drops/kalshi_sports_executable_horizon_labels/` |
