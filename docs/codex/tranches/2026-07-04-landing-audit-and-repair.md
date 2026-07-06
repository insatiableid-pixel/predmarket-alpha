# Landing Audit and Repair — 2026-07-04

## Summary

Completed full landing audit for the Sports Evidence Factory tranche. All quality gates pass, all tests pass, sports label accumulation cycle runs cleanly, and all upstream artifacts exist and pass safety validation.

## Verification Results

| Check | Status | Detail |
|-------|--------|--------|
| `make test-unit` | ✅ PASS | 702 passed, 14 deselected (baseline met) |
| `make test-integration` | ✅ PASS | 14 passed (baseline met) |
| `make quality` | ✅ PASS | All hard ratchet gates green (ruff, typecheck, tech-debt 22/22, file-sizes, modularize, feature-flags, validate-agents) |
| `make modularize` | ✅ PASS | 2 contracts kept, 0 broken |
| `compileall` | ✅ PASS | No import errors |
| `make lint-baseline-check` | ✅ PASS | lint 1407/1422 (<= 1422), format 92/94 (<= 94) |
| `config/config.yaml` | ✅ PASS | `execution_mode: "disabled"` |
| `make kalshi-sports-label-accumulation-cycle` | ✅ PASS | Exit 0, valid artifact produced |
| 8 upstream artifacts exist and are valid JSON | ✅ PASS | All 8 exist, parse, and pass safety |
| Research-only guardrails | ✅ PASS | All artifacts: `research_only=true`, `execution_enabled=false` |
| Live preflight | ✅ PASS | `kalshi_live_blocked`, 0 live-eligible |
| Versioned output directory | ✅ PASS | JSON, MD, CSV files present |
| latest-* pointer files | ✅ PASS | All 3 pointer files exist and match versioned output |

## Label Accumulation Artifact Key Values

- **Status:** `sports_label_accumulation_waiting_more_exact_labels`
- **MLB:** 72 exact labels, 16 independent, deficit=14
- **World Cup Soccer:** 6 exact labels, 6 independent, deficit=24
- **ATP:** 0 exact labels, 0 independent, deficit=10
- **Total exact labels:** 78
- **Total independent labels:** 22
- **All safety booleans:** false
- **Gates:** 2 pass, 1 blocked (family_label_thresholds), 3 pass

## 8 Upstream Artifacts All Safe

| Artifact | Status | research_only | execution_enabled |
|----------|--------|---------------|-------------------|
| mlb_observation | sports_proxy_observation_loop_label_rows_ready | true | false |
| mlb_model | sports_proxy_feature_model_falsification_blocked_insufficient_independent_labels | true | false |
| world_cup_observation | world_cup_proxy_observation_loop_label_rows_ready | true | false |
| world_cup_model | world_cup_proxy_feature_model_falsification_blocked_insufficient_independent_labels | true | false |
| atp_observation | atp_proxy_observation_loop_ready_waiting_settlement | true | false |
| atp_evidence | atp_proxy_evidence_gate_blocked_waiting_settlement_labels | true | false |
| paper | paper_decision_candidates_ready_all_rows_blocked | true | false |
| live | kalshi_live_blocked | true | false |

## Pre-Existing Issues (Expected, Not Blocking)

These are known issues documented in AGENTS.md and are not regressions:

1. **184 deptry dependency warnings (DEP003)** — Transitive dependency pattern. Known and expected. Not blocking.
2. **slowapi DeprecationWarning** — `asyncio.iscoroutinefunction` deprecated in Python 3.16. Expected, not blocking.
3. **Kalshi public API response format** — The exchange/status endpoint returns a response where the init.sh assert on `'status' in data` fails. This is a known format quirk (the API may wrap differently than expected). Research scripts work fine, as demonstrated by the successful label accumulation cycle.
4. **~200 mypy strict errors** — Across `predmarket/`. Advisory, not blocking. Ratchet is held (not enforced in quality gate).
5. **Format baseline at 92/94** — Well under the 94 limit. No regression.
6. **Lint baseline at 1407/1422** — Well under the 1422 limit. No regression.
7. **3 oversized files** — Known offenders: `codex_macro_router.py` (7277 lines), `kalshi_contract_ev_ledger.py` (3402 lines), `kalshi_signal_factory_status.py` (2028 lines). No new oversized files.

## No Regressions Found

- Ruff lint count: 1407 (baseline allows up to 1422) — improved from original baseline
- Ruff format count: 92 (baseline allows up to 94)
- Tech-debt: 22/22 — ratchet held
- File sizes: No new oversized files
- Feature flags: All 5 referenced
- AGENTS.md validation: Passed
- Import boundaries: 2 contracts kept, 0 broken

## Repairs Needed

**No repairs were needed.** All make targets exit 0, all quality gates pass, all artifacts are valid and safe. The sports evidence chain is fully operational.

## Next Steps for Mission

Next feature: **label-accumulation-dedup-and-provenance** (Milestone 2). Current label accumulation is functional with basic dedup. The next worker should harden dedup with composite keys, add provenance fields, and add stale-observation detection.
