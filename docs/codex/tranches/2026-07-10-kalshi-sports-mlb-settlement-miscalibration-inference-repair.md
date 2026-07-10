# Tranche: Repair MLB settlement-miscalibration inference (PR #71)

Date: 2026-07-10  
Branch: `codex/kalshi-sports-mlb-miscalibration-20260710T050210Z`  
Worktree: `/home/mrwatson/projects/predmarket-alpha-worktrees/kalshi-sports-mlb-miscalibration-20260710T050210Z`  
Directive: `GROK_KALSHI_SPORTS_MLB_INFERENCE_REPAIR_DENSE_PANEL_DIRECTIVE_20260710T052849Z.md`  
Base at branch tip before repair: `5b056a87f848480148c85262d734aa4b9e82ba29`  
PR: https://github.com/insatiableid-pixel/predmarket-alpha/pull/71

## Phase 0 landing reconciliation

| Fact | Verified |
|---|---|
| PR #69 / #70 merged | Yes (ancestors of PR head include both merges) |
| PR #71 open | Yes, MERGEABLE |
| Head SHA at start | `5b056a87f848480148c85262d734aa4b9e82ba29` |
| Worktree | clean except untracked `.venv` symlink (not staged) |
| CI at start | green (lint, code-quality, security, Semgrep, gitleaks, py3.12/3.13) |
| Canonical checkout | dirty + diverged; left untouched |
| Prior labeled rows / events | 1168 / 175 (reproduced from saved inputs) |
| Prior claim Outcome B | Overclaim — mandatory repairs applied before merge |

## Defects repaired

1. **Economic test** — replaced win-rate binomial mislabeled as `p_value_mean_net_positive` with slate-clustered sign-flip test of `E[fee-adjusted net] > 0` (`p_economic`). Win rate is descriptive only.
2. **Calibration inference** — added `p_calibration` on direction-adjusted residual with same cluster discipline; `p_joint = max(p_economic, p_calibration)`.
3. **FDR** — BH on `p_joint` for powered **novel** members only; controls excluded and recorded.
4. **Lifecycle** — per-spec power; family falsified only when every novel member is resolved without survivor; underpowered blocks Outcome B.
5. **Breadth vs falsification** — inference pass + slate-share fail → `frozen_candidate_waiting_multi_slate_confirmation`.
6. **Timestamps** — `historical_discovery_data_cutoff_utc` vs `forward_confirmation_registered_at_utc`; runtime cutoff provenance documented as non-preregistration.
7. **Fees** — `resolve_kxmlbgame_taker_fee` with type/multiplier/source/fallback provenance; conservative general quadratic offline default.
8. **Capture readiness** — `capture_infrastructure_ready` vs `evidence_panel_ready`; status `capture_infrastructure_ready_panel_insufficient_slate_breadth`.
9. **Clustering diagnostics** — chronological slate-date buckets; event collapse for complements/duplicates; cluster bootstrap CI.

## Regenerated evidence (saved inputs, no network)

```bash
.venv/bin/python scripts/kalshi_sports_mlb_settlement_miscalibration.py \
  --no-fetch-public-settlements \
  --discovery-cutoff-utc 2026-07-10T05:18:29Z \
  --observation-dir .../kalshi_sports_microstructure_observations \
  --observation-dir .../kalshi_sports_proxy_observations \
  --observation-dir .../kalshi_sports_mlb_settlement_miscalibration \
  --settlement-dir .../kalshi_sports_microstructure_settlements \
  --settlement-dir .../kalshi_sports_settlements \
  --settlement-dir .../kalshi_sports_mlb_settlement_miscalibration
```

### Corrected family state

- **Status:** `mlb_settlement_miscalibration_confirmation_pending`
- **Family status:** `confirmation_pending` (not Outcome B)
- Labeled rows: 1168; distinct events: 175
- Novel specs: 7
  - powered: 1
  - underpowered: 6
  - powered_falsified: 0
  - frozen multi-slate confirmation: 1
  - research-ready survivors: 0

### Frozen candidate (do not retune)

- `tight_spread_favorite_buy_yes_t60m`
- formula_hash: `9cd76b9703cd167988fd94d53a9cc82ed9b37a7e3b30f316796f9dbb46cfa56d`
- oos events=20, oos slates=6, mean_net≈0.0946, p_joint≈0.0005, q≈0.0005
- fails largest slate share (0.50 > 0.35) → waiting multi-slate confirmation
- `path_slope_continuation_buy_yes_t60m` remains **underpowered** (5 slates < min inference slates=6) despite positive descriptive mean net

### Capture / panel

- capture_infrastructure_ready: true
- evidence_panel_ready: false
- status: `capture_infrastructure_ready_panel_insufficient_slate_breadth`

## Verification

```bash
.venv/bin/python -m pytest -q tests/test_kalshi_sports_mlb_settlement_miscalibration.py  # 13 passed
```

Full suite / lint / kalshi-verify run before merge.

## Next permissible action after merge

1. Fresh worktree from repaired `origin/main`.
2. Preregister dense multi-slate MLB panel (primary T-60m / T-15m).
3. Operate restart-safe read-only capture; no modeling until `evidence_panel_ready`.
4. Evaluate frozen candidate once at registered confirmation power only.

## Safety

- Research-only; no live execution, sizing, accounts, orders, credentials.
- Canonical dirty checkout preserved.
- `.venv` symlink not committed.
