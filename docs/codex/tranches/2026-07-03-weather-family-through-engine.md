# Weather Family Through Engine (Milestone 4)

## Outcome

Added the weather family (KXHIGH/KXLOW temperature contracts) as the third signal family through the SignalFamily engine, proving the abstraction makes adding families cheap with zero edits to the generic spine modules. Three families (crypto + sports + weather) now coexist in status/scout/router. The M3-ENGINE-HARDENING (scrutiny-surfaced `status_prefix` field + `_falsification_status()` fix) was applied to prevent misrouting of weather status strings.

## Evidence

- `make kalshi-weather-proxy-feature-packet` -> `weather_proxy_feature_packet_ready` with 168 real weather features; all rows `usable=false`.
- `make test-unit` -> all 589 unit tests pass (+ 11 integration).
- Crypto characterization tests (143) unchanged; sports tests (90) unchanged; status tests (29) unchanged.
- `git diff predmarket/engine.py predmarket/shared_helpers.py` -> only the `_falsification_status()` fix (spine closed for modification).
- Real public-data weather feature-packet artifact: `docs/codex/macro/latest-kalshi-weather-proxy-feature-packet.json`.

## Learned

- The `status_prefix` field was essential since the old `_falsification_status()` used `"crypto" in family_id` substring matching which would have misrouted `"weather_proxy"` to `"sports_proxy"` instead.
- Weather contracts use a different date/time structure (daily settlement vs intraday crypto). The close-time window default of 48 hours works well.
- The NWS api.weather.gov is truly keyless and responds well — no auth needed.

## Next Route

Complete the weather lane through the full falsification/replay/CCD/cluster-control chain, then land the formal theorem doctrine and cross-family integration finalization (Milestone 5).

## Guardrail

Weather remains research-only (`usable=false`, `execution_enabled=false`). Raw NWS payloads must stay outside the repo under `manual_drops/kalshi_weather_proxy_features/`. The weather observation loop emits labels only from Kalshi public settlement, never from the NWS proxy.
