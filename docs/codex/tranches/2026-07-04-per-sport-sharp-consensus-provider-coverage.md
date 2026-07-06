# Per-Sport Sharp Consensus Provider Coverage

Date: 2026-07-04

## Objective

Continue implementing the Claude sports advice by preventing a covered ATP/Wimbledon donor feed from masking provider gaps in other Kalshi sports. The sports sharp no-vig consensus lane should be judged per target sport, not globally.

## Landing

- Added per-sport target coverage to `predmarket/sports_consensus_provider_policy.py`.
- Added `--target-sports` to `scripts/kalshi_sports_consensus_provider_audit.py`.
- Added `make kalshi-sports-consensus-provider-audit`.
- Wired provider audit into `make kalshi-sports-consensus-observation-watch-once` and `make kalshi-sports-evidence-cycle`.
- Surfaced provider audit status, covered sports, target count, and gap count in the sports evidence cycle report.

## Current Evidence

Latest provider audit status: `sports_consensus_provider_audit_ready_with_per_sport_gaps`.

- Target sports: `mlb`, `tennis`, `soccer`, `nfl`, `nba`.
- Covered sports: `tennis`.
- Gap count: `4`.
- MLB: `secondary_only` (`lowvig`, `betonlineag`), no strict anchor.
- Soccer: `missing_asian_sharp_reference`.
- NFL: `missing_strict_consensus`.
- NBA: `missing_strict_consensus`.

Latest sports consensus falsification status remains `sports_consensus_falsification_blocked_insufficient_labels` with `16` joined labels, `8` independent labels, `3` OOS labels, `0` tested hypotheses, and `0` FDR survivors.

Latest paper and live state remains blocked: `0` paper-usable rows, `$0` paper stake, `0` live-eligible rows, and `$0` live stake.

## Verification

- Focused tests: `17 passed`.
- Touched-file Ruff check/format passed.
- `make kalshi-sports-consensus-provider-audit` exits `0`.
- `make kalshi-sports-evidence-cycle-report` exits `0`.
- `make kalshi-always-on-collector-once` exits `0`.

## Guardrails

- Audit only.
- No threshold lowering.
- No probabilities, EV, paper stake, or live eligibility from provider coverage alone.
- No provider/API call added by the audit itself.
- Existing research-only and no account/order path invariants remain intact.

## Next Action

Upgrade actual sharp reference coverage for MLB, soccer, NFL, and NBA. Soccer needs Asian sharp anchors such as SBOBet/Singbet/IBC or an equivalent strict source before the World Cup lane should be considered covered. Keep the collector running until the consensus lane reaches at least `30` independent labels and `10` OOS labels, then let OOS/FDR decide.
