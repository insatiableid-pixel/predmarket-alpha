# Weather Family Through Engine — Milestone 4

## Summary

Added the weather family (KXHIGH/KXLOW temperature contracts) through the SignalFamily engine as the third signal family, proving the abstraction makes adding families cheap with zero edits to the generic spine modules. The spine is confirmed closed for modification (git diff of `predmarket/engine.py` and `predmarket/shared_helpers.py` shows only the `_falsification_status()` hardening fix). Three families (crypto + sports + weather) now coexist in status/scout/router. The M3-ENGINE-HARDENING (scrutiny-surfaced `status_prefix` field) was applied to prevent misrouting of weather status strings.

## What Changed

- **M3-ENGINE-HARDENING:** Added `status_prefix` field to `SignalFamily` dataclass. Fixed `_falsification_status()` to use `status_prefix` (or `family_id` fallback) instead of substring matching on `family_id` which would have misrouted weather. Updated `crypto_family.py` and `sports_family.py` to set their respective `status_prefix` values.
- **`predmarket/weather_family.py`** (new): `WeatherProxyFamily` descriptor with station/gridpoint resolver (`api.weather.gov` keyless feed), NWS forecast + observation bracket feature model, `station|bracket|date` cluster key, and `weather_bracket_directional_accuracy` model evaluator.
- **`scripts/kalshi_weather_proxy_feature_packet.py`** (new): Weather feature-packet builder (filters KXHIGH/KXLOW contracts, resolves NWS station/gridpoint, fetches forecast + observations, computes bracket probability, every row research-only).
- **`scripts/kalshi_weather_proxy_observation_loop.py`** (new): Weather observation/label loop (archives observations deduped by observation_id, emits labels from Kalshi public settlement only).
- **Makefile:** Added `kalshi-weather-proxy-feature-packet`, `kalshi-weather-proxy-feature-watch-once`, `kalshi-weather-proxy-observation-loop`, `kalshi-weather-proxy-observation-watch-once` targets.
- **`scripts/kalshi_signal_factory_families.py`**: Added weather family ID, capability names, tranche map, capability builder, status computation, and three-family `select_leading_family`.
- **`scripts/kalshi_signal_factory_status.py`**: Added weather artifact paths to `Artifacts` dataclass (isolated + from_macro_dir), weather data loading + capabilities + status in `build_signal_factory_status`, weather paths in `parse_args` and `main`.
- **`tests/test_kalshi_weather_proxy_feature_packet.py`** (new): 18 artifact-replay tests for the weather feature packet (filtering, schema, safety, station resolver, bracket prediction).
- **`tests/test_kalshi_weather_proxy_observation_loop.py`** (new): 8 tests for the observation loop (snapshotting, dedup, label emission, research-only safety).

## Latest Evidence

- `make kalshi-weather-proxy-feature-packet` -> `weather_proxy_feature_packet_ready` with 168 real weather feature rows; all `usable=false`, `research_only=true`, `execution_enabled=false`.
- `make test-unit` -> 589 passed, 11 deselected.
- Crypto characterization tests (143) unchanged; sports tests (90) unchanged; status tests (29) unchanged.
- Three families in `latest-kalshi-signal-factory-status.json`: `crypto_proxy` (capacity_depth_blocked), `sports_baseball` (ccd_blocked), `weather_proxy` (feature_packet_ready).

## Artifacts

- `docs/codex/macro/latest-kalshi-weather-proxy-feature-packet.{json,md,csv}`
- `docs/codex/macro/latest-kalshi-weather-proxy-observation-loop.{json,md,csv}`
- `docs/codex/macro/latest-kalshi-signal-factory-status.{json,md}` (shows 3 families)

## Verification

- All 26 weather tests pass (18 feature packet + 8 observation loop)
- All 600 total unit tests pass
- All 5 binding quality gates pass
- Real public-data weather run succeeds with honest research-only artifacts

## Safety

- Weather remains research-only: `usable=false`, `execution_enabled=false` on every artifact row
- No execution, account, order, or DB-write paths
- Raw NWS payloads written outside the repo under `manual_drops/kalshi_weather_proxy_features/`
- No paid API calls (api.weather.gov is keyless)
- No regression on crypto or sports lanes

## Next Blocker

Complete the weather lane through the full falsification/replay/CCD/cluster-control chain, then land the formal theorem doctrine and cross-family integration finalization (Milestone 5).
