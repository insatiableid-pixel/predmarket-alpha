# Weather Station Provenance And Family Cycle

Date: 2026-07-03

## Objective

Attack the active Kalshi signal-factory bottlenecks while preserving the north-star guardrails:
no discretion, broad family intake, hard falsification, zero usable rows until gates pass.

## What Changed

- Fixed crypto signal-factory routing precedence for `crypto_proxy_capacity_correlation_decay_blocked_no_current_candidates`.
  The status now routes no-current-candidate states to observation accumulation instead of mislabeling them as missing depth.
- Ran the current safe family cycles:
  - Crypto: refreshed observations and downstream gates; current candidates returned, depth/correlation are controlled, decay survival still blocks.
  - Sports: 58 MLB observations archived, waiting for public settlement labels.
  - ATP: observation/evidence gate refreshed, still waiting for public settlement labels.
  - Weather: feature/observation/falsification/replay/CCD/cluster chain refreshed.
- Fixed weather station resolution for current Kalshi ticker shapes such as `KXHIGHMIA` and `KXLOWTSFO`.
  The weather feature packet now resolves 480 rows across 20 stations instead of defaulting all rows to `KNYC`.
- Hardened weather falsification against poisoned labels.
  Any weather label whose station provenance conflicts with the contract ticker is now rejected before OOS/FDR.
- Added explicit `station_provenance_matches_ticker` gate to the weather falsification report.
- Trimmed decorative banners from `scripts/kalshi_sports_proxy_feature_packet.py` so the file-size ratchet passes without regenerating the baseline.

## Latest Evidence

- Crypto status: `signal_factory_crypto_proxy_decay_survival_blocked`.
- Crypto CCD after refresh: 60 current candidates, 60 orderbooks, positive depth present, decay still blocked.
- Weather feature packet: 480 rows, 20 station IDs, 24 rows per station.
- Weather falsification: 360 raw historical label rows, 360 station mismatches, 0 valid labels, status `weather_proxy_feature_model_falsification_blocked_missing_labels`.
- The historical weather rows are no longer counted as evidence; future post-fix settled labels will enter normally.

## Verification

- `make quality`
- `make test-unit` -> 659 passed, 14 deselected
- `make test-integration` -> 14 passed
- Focused:
  - `tests/test_kalshi_weather_proxy_feature_packet.py`
  - `tests/test_kalshi_weather_proxy_feature_model_falsification.py`
  - `tests/test_kalshi_weather_proxy_observation_loop.py`
  - `tests/test_kalshi_signal_factory_status.py`
  - `tests/test_kalshi_sports_proxy_feature_packet.py`

## Next Bottleneck

The factory is mostly time-blocked on settlement evidence:

- Crypto needs repeated settled buckets until recent decay survival is no longer below random.
- Sports and ATP need public Kalshi settlement labels for the already archived observations.
- Weather needs fresh post-fix station-correct observations to settle; historical bad-station labels are intentionally excluded.

Do not lower sample, decay, station-provenance, or FDR thresholds. No usable EV, paper stake, sizing, or live execution is authorized by this tranche.
