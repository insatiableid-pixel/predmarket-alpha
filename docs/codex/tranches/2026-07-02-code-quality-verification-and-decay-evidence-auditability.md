# 2026-07-02 Code-Quality Verification, Writer Bug Repair, and Decay Evidence Auditability

## Phase 1: Quality Tranche Verification and Repair

### Verified

- Inspected `pyproject.toml`, quality Make targets, `.pre-commit-config.yaml`,
  `.github/workflows/ci.yml` code-quality job, ratchet baselines
  (`.ruff-baseline.json`, `.tech-debt-baseline.json`, `.large-file-baseline.json`),
  and quality scripts (`scripts/scan_tech_debt.py`, `scripts/check_file_sizes.py`).
- All four hard quality gates pass:
  - `make lint-baseline-check`: lint 1410/1410, format 90/90.
  - `make tech-debt-check`: 20/20.
  - `make file-sizes-check`: no new oversized files.
  - `make modularize`: 2 contracts kept, 0 broken.

### Repaired: 3 pre-existing test failures

- `test_ccd_writer_skips_latest_for_tmp_out_dir_by_default`
- `test_cluster_control_writer_skips_latest_for_tmp_out_dir_by_default`
- `test_signal_factory_writer_skips_latest_for_tmp_out_dir_by_default`

Root cause: `path_is_within(out_dir, CONTROL_REPO)` was too broad. When pytest's
`tmp_path` lives under `.tmp/` inside the repo (as it does with
`TMPDIR=.tmp`), the heuristic returned `True`, so the writer created latest
pointers into the real macro dir from test output.

Fix: narrowed the heuristic from `CONTROL_REPO` (repo root) to `MACRO_DIR`
(`docs/codex/macro`) in all three writers:
- `scripts/kalshi_signal_factory_status.py:write_signal_factory_status()`
- `scripts/kalshi_crypto_proxy_capacity_correlation_decay.py:write_crypto_proxy_capacity_correlation_decay()`
- `scripts/kalshi_crypto_proxy_correlation_cluster_control.py:write_crypto_proxy_correlation_cluster_control()`

Production calls with `DEFAULT_OUT_DIR` (under `MACRO_DIR`) still write latest
pointers. Test calls with tmp paths correctly skip them.

Confirmed pre-existing: the tests fail identically with `kalshi_dataset.py`
stashed. The `kalshi_dataset.py` diff adds filter params and `fetch_series_list`;
it does not touch writer logic.

## Phase 2: Decay Evidence Auditability Improvement

### Change

Enriched `decay_summary()` in `scripts/kalshi_crypto_proxy_research_candidate_replay.py`
to return full per-bucket auditability without changing any gate threshold:

- `decay_buckets`: list of per-bucket objects with `bucket`, `label_count`,
  `correct_count`, `accuracy`, and `pass_threshold` (chronologically ordered).
- `total_decay_labels`: total labels across all buckets.
- `passing_bucket_count`: buckets with accuracy >= 0.5.
- `cumulative_accuracy`: accuracy across all buckets.
- `recent_bucket_key` and `recent_bucket_label_count`.

Surfaced these in `build_summary()` and enriched the `decay_survival_available`
gate reason to include the full per-bucket breakdown.

Propagated the enriched detail through the CCD
(`scripts/kalshi_crypto_proxy_capacity_correlation_decay.py`): `build_summary()`
now carries `replay_recent_bucket_key`, `replay_recent_bucket_accuracy`,
`replay_recent_bucket_label_count`, `replay_total_decay_labels`,
`replay_cumulative_decay_accuracy`, `replay_passing_bucket_count`, and
`replay_decay_buckets`. The CCD `decay_survival` gate reason now includes the
same breakdown.

### Thresholds preserved (unchanged)

- Recent-bucket accuracy gate: >= 0.5 (not worse than random).
- `min_decay_buckets`: 3.
- `min_decay_labels`: 100.
- `min_side_oos_labels`: 30.

### Latest decay evidence (refreshed)

- Decay status: `recent_bucket_below_random` (gate still blocked, correct).
- Recent bucket: `2026-07-02T05:00Z`, accuracy 0.333, 9 labels.
- Cumulative accuracy: 0.6 across 95 labels.
- Passing buckets: 3/4 (T01:15Z=0.75, T01:45Z=0.89, T02:00Z=0.58; T05:00Z=0.33).
- Usable rows: 0.

### Guardrails preserved

- `usable_row_count=0` in replay, CCD, cluster control, and signal factory.
- `research_only=True`, `execution_enabled=False` in all artifacts.
- `market_execution=False`, `account_or_order_paths=False`,
  `staking_or_sizing_guidance=False`.
- All 315 replay rows have `usable=False`.
- No paper overlay, sizing, execution, or account/order paths added.

## Tests

- 410 unit tests pass (was 407 + 3 failures).
- 3 new tests for decay detail fields.

## Verification Commands

```bash
# Phase 1: quality gates
make lint-baseline-check
make tech-debt-check
make file-sizes-check
make modularize
make quality

# Phase 1: previously-failing tests now pass
TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest \
  tests/test_kalshi_crypto_proxy_capacity_correlation_decay.py \
  tests/test_kalshi_crypto_proxy_correlation_cluster_control.py \
  tests/test_kalshi_signal_factory_status.py \
  -q --tb=short -m "not integration"

# Phase 1+2: full unit suite
TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest tests/ -q --tb=short -m "not integration"

# Phase 2: decay detail tests
TMPDIR=.tmp PYTHONPATH=. .venv/bin/pytest \
  tests/test_kalshi_crypto_proxy_research_candidate_replay.py \
  -q --tb=short -m "not integration"

# Phase 2: refresh macro artifacts
make kalshi-crypto-proxy-research-candidate-replay
make kalshi-crypto-proxy-capacity-correlation-decay
make kalshi-crypto-proxy-correlation-cluster-control
make kalshi-signal-factory-status
make macro-route

# Phase 2: guardrail verification
.venv/bin/python -c "
import json
for f in ['latest-kalshi-crypto-proxy-research-candidate-replay',
          'latest-kalshi-crypto-proxy-capacity-correlation-decay',
          'latest-kalshi-signal-factory-status']:
    d = json.load(open(f'docs/codex/macro/{f}.json'))
    s = d.get('summary', d)
    assert s.get('usable_row_count', 0) == 0, f'{f} has usable rows'
    assert d.get('research_only') is True
    assert d.get('execution_enabled') is False
    print(f'{f}: usable=0, research_only=True, execution=False')
print('All guardrails preserved.')
"
```
