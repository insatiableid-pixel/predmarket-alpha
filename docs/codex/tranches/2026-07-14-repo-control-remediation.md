# 2026-07-14: Repository Control Remediation

## What

Remediated the unauthorized merge commit `63fca31` (created via
`git merge --no-edit -X theirs` on branch
`codex/repo-control-mlb-sharp-lag-20260714`). Built a V2 integration tree
on `origin/main` (`c78eed9`) that preserves the correct origin baseline
plus verified source code from origin/main. All R0–R4 evidence gates pass.

## Root Cause of V1 Failure

The prior session's `-X theirs` merge selected the **local** side for every
conflict. This was disastrous because:
- Local `shared_helpers.py` is 453 lines and missing `manual_drop_path`;
  origin's is 482 lines with the function → sports consensus imports break
- For **every** DIFF file (predmarket + scripts + tests), origin's version
  has **more lines** than local's → origin is more feature-complete
- Origin has 6 `predmarket/` modules, 4 `scripts/`, and 3 `tests/` that
  local doesn't have at all (dense ops, settlement miscalibration, portfolio
  risk, etc.)

## V2 Correction

V2 starts from `origin/main` and **keeps origin's version for every DIFF
file**. This is the correct baseline because:
1. Origin has `manual_drop_path`/`configured_path`/`project_path` in
   `shared_helpers.py` — local doesn't
2. Origin has `paper_portfolio_risk.py`, `sports_mlb_dense_panel.py`,
   `sports_mlb_settlement_miscalibration_eval.py`, and 10 other modules
   that local is missing
3. Every DIFF predmarket file has more lines in origin (avg +11%) —
   origin is more complete
4. Every DIFF script file has more lines in origin
5. Every DIFF test file has more lines in origin

We repaired and completed all R2 controls (credential mode validation, QuotaBudget checks and header reconciliation, call metadata accounting, outer deadline request timeouts, and collector.log retention limits).

## Verification Results

| Gate | Result |
|------|--------|
| make check-env | PASS |
| Focused sports suite | **54 passed** |
| Full unit suite (make test-unit) | **1,524 passed** |
| Integration suite (make test-integration) | **14 passed** |
| Kalshi verification (make kalshi-verify) | **53 passed** |
| Lint baseline | 101 pre-existing errors (within ratchet) |
| **TOTAL** | **1,645 passed, 0 failed** |

## Phases Completed

### Phase 0 — R0 Evidence Manifest ✓
- `docs/codex/artifacts/r0-corrected-incident-manifest-20260714.json`
  with correct preflight SHA-256, per-worktree status, all 271 untracked
  files, crontab, confirmation state, `manual_drop_path` root cause

### Phase 1 — Commit Audit ✓
- `docs/codex/artifacts/commit-disposition-corrected-ledger-20260714.json`
  with 43 content-classified rows (41 clean/superseded, 2 cosmetic/deferred),
  corrected summary counts, and per-file decisions for V2
- Commit `63fca31` quarantined (not deleted, rebased, or modified)

### Phase 2 — Legitimate Integration Tree ✓
- V2 at `repo-control-mlb-sharp-lag-20260714-v2` from `origin/main=c78eed9`
- 5 untracked files (artifacts/tests) — 10 modified files (repaired files)

### Phase 3 — Per-File Merge Decisions ✓
- All DIFF files resolved to origin version (documented in ledger)
- Origin version is correct baseline for every DIFF file
- No local source code improvements to merge

### Phase 4 — Verification (R4) ✓
- Durable log at `docs/codex/artifacts/r4-verification-log-20260714.txt`
- All 1,645 tests pass across focused, unit, integration, and kalshi-verify gates

### Phase 5 — Preservation ✓
- `63fca31` quarantined; both histories preserved; all 10 worktrees intact
- Crontab untouched at `c78eed9` on ops worktree
- Secrets untouched (secure key at `~/.secrets/the-odds-api/key.txt` mode 600;
  legacy at `manual_drops/secrets/the_odds_api_key.txt` mode 777)
- No commits, merges, pushes, or PRs made to main branch
- V2 has **10 modified files**, 5 untracked files

### Phase 6 — Authorization Gate (REACHED, V2 complete)
- All evidence collected and verified
- Ready for explicit user authorization to commit V2

## Repository State

- **quarantined:** `codex/repo-control-mlb-sharp-lag-20260714` @ 63fca31
  (untouched, preserved as evidence)
- **active:** `codex/repo-control-mlb-sharp-lag-20260714-v2` from
  `origin/main=c78eed9` (10 modified, 5 untracked files)
- **cron:** `kalshi-sports-mlb-dense-panel-ops-origin-main-20260710T170600Z`
  @ c78eed9 (untouched)
- **canon:** `main` @ `e431ae2` (intact)
