# 2026-07-07 Fable Sports Evidence Path Config

## Landing

Removed the remaining machine-specific local roots from Fable-critical sports evidence acquisition scripts:

- `scripts/kalshi_atp_proxy_observation_loop.py`
- `scripts/kalshi_sports_proxy_observation_loop.py`
- `scripts/kalshi_sports_microstructure_observation_loop.py`
- `scripts/kalshi_sports_proxy_feature_model_falsification.py`
- `scripts/kalshi_sports_proxy_capacity_correlation_decay.py`

The scripts now use `manual_drop_path()` and `project_path()` defaults for donor project paths, Kalshi settlement snapshots, observation packets, label packets, and raw orderbook captures. CLI flags and Make contracts are unchanged, so existing workstation behavior remains the default while relocated clones can use `PREDMARKET_MANUAL_DROPS_ROOT` and `PREDMARKET_PROJECTS_ROOT`.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_path_defaults.py -q` -> `10 passed`
- `TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/ruff check scripts/kalshi_atp_proxy_observation_loop.py scripts/kalshi_sports_proxy_observation_loop.py scripts/kalshi_sports_microstructure_observation_loop.py scripts/kalshi_sports_proxy_feature_model_falsification.py scripts/kalshi_sports_proxy_capacity_correlation_decay.py tests/test_kalshi_path_defaults.py` -> `All checks passed`
- Hardcoded root scan over the touched sports evidence scripts found no `/home/mrwatson/manual_drops` or `/home/mrwatson/projects` matches.
- Make dry-runs passed for:
  - `kalshi-atp-proxy-observation-loop`
  - `kalshi-sports-proxy-observation-loop`
  - `kalshi-sports-microstructure-observation-watch-once`
  - `kalshi-sports-proxy-feature-model-falsification`
  - `kalshi-sports-proxy-capacity-correlation-decay`
- `git diff --check` clean for touched files.
