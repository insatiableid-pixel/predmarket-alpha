# Tranche: Weather Falsification, Replay, CCD, and Cluster Control Gates

## Outcome

Completed the weather lane through the full downstream gate chain via the SignalFamily engine — zero edits to the generic spine. Added 4 new scripts (falsification, replay, CCD, cluster control), 4 Make targets wired into `kalshi-weather-proxy-observation-watch-once`, and 27 artifact-replay tests. Three families (crypto, sports, weather) now have complete end-to-end gate chains through the shared engine.

## Evidence

- 27 new artifact-replay tests pass (TDD: red → green)
- 616 total unit tests pass (crypto 143 + sports 90 + router 53 + weather 27 + others unchanged)
- All 5 binding quality gates green (lint, tech-debt, file-sizes, modularize, AGENTS.md)
- Zero spine edits (`git diff --name-only predmarket/engine.py predmarket/shared_helpers.py predmarket/signal_family.py` = empty)
- All new scripts clean on `ruff check`

## Learned

The engine's generic `build_falsification()`, `build_replay_calibration()`, `ask_levels()`, `capacity_row()`, `build_decay_summary()`, and `controlled_capacity_rows()` functions required zero modification to accept the WeatherFamily descriptor — the abstraction is verified closed for modification.

## Next Route

Paper probability overlay for weather (post-mission) or macro_econ family addition. Weather observations/labels accumulate for eventual falsification.

## Guardrail

Every row remains `usable=false`, `calibrated_probability=null`, `research_only=true`, `execution_enabled=false`. No execution/account/order paths exist. Wx observations still accumulating for falsification threshold.
