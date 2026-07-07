# 2026-07-07 Fable World Cup ATP Replay Path Config

## Landing

Removed machine-specific local roots from the remaining World Cup, ATP, and sports replay evidence surfaces:

- `scripts/kalshi_world_cup_proxy_observation_loop.py`
- `scripts/kalshi_world_cup_proxy_feature_model_falsification.py`
- `scripts/kalshi_world_cup_outcome_independence_diagnostic.py`
- `scripts/kalshi_atp_proxy_evidence_gate.py`
- `scripts/kalshi_sports_proxy_research_candidate_replay.py`
- `scripts/kalshi_sports_blocker_clearance_cycle.py`

Defaults now use `manual_drop_path()` for local evidence drops and `project_path()` for donor repo artifacts. Existing CLI overrides, Make targets, and evidence semantics are unchanged.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_path_defaults.py -q` -> `12 passed`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/ruff check ...` over touched files -> `All checks passed`
- Hardcoded root scan over touched runtime files found no `/home/mrwatson/manual_drops` or `/home/mrwatson/projects` matches.
- Make dry-runs passed for:
  - `kalshi-world-cup-proxy-observation-loop`
  - `kalshi-world-cup-proxy-feature-model-falsification`
  - `kalshi-world-cup-outcome-independence-diagnostic`
  - `kalshi-atp-proxy-evidence-gate`
  - `kalshi-sports-proxy-research-candidate-replay`
  - `kalshi-sports-blocker-clearance-cycle`
- `git diff --check` clean for touched files.
