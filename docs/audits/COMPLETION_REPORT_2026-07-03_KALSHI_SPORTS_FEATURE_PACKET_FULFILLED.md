# COMPLETION REPORT — Kalshi Sports Feature Packet (Milestone 1)

**Date:** 2026-07-03
**Scope:** `sports-feature-packet` (Milestone 1 — sports-feature-foundation)
**Status:** Fulfilled

## Summary

Built the baseball feature-packet builder (`scripts/kalshi_sports_proxy_feature_packet.py`), the sports analog of `scripts/kalshi_crypto_proxy_feature_packet.py`. It joins open Kalshi MLB/KBO/LMB game-winner contracts (`KXMLBGAME`/`KXKBOGAME`/`KXLMBGAME`) to pre-game strength features from keyless public feeds (MLB Stats API for MLB, ESPN hidden API for KBO/LMB) and emits a MODEL-FEATURES artifact with a strength-derived prediction. Every row is research-only (`usable=false`, `calibrated_probability=null`); no execution/account/order paths. This is a distinct artifact from the Type 2 sportsbook-reference lane (no margin/divergence/american-odds fields).

## What Changed

- **New module** `scripts/kalshi_sports_proxy_feature_packet.py` (1228 lines): `build_sports_proxy_feature_packet` / `write_sports_proxy_feature_packet` / `main`; per-league team-identity resolver (MLB via statsapi schedule, KBO/LMB via ESPN scoreboard); keyless feature fetcher with injectable `fetch_json`; frozen-coefficient pre-game strength model (standings win% + pythagorean -> sigmoid); mechanical `|p_win - yes_ask| >= tau` prediction rule; close-time-windowed, capped, ticker-deduped selection; report envelope + gates + `latest-*` pointers mirroring the crypto template.
- **New frozen-coefficient artifact** `docs/codex/macro/sports-baseball-strength-coefficients.json` (fit-once-then-frozen provenance; never refit at decision time).
- **New tests** `tests/test_kalshi_sports_proxy_feature_packet.py` (28 artifact-replay cases covering VAL-SFL-001..025, 033, 035..039, 041..045): importlib load, synthetic Kalshi + statsapi/ESPN fixtures in `tmp_path`, injected `fetch_json` (no network), assert routed status/gates/rows.
- **Makefile**: added `kalshi-sports-proxy-feature-packet` target + variables + `.PHONY` + help text.
- **Codex runway**: prepended a landing to `docs/codex/current-state.md`; tranche note `docs/codex/tranches/2026-07-03-sports-feature-packet.md`; this completion report.
- **Latest artifacts**: `docs/codex/macro/latest-kalshi-sports-proxy-feature-packet.{json,md,csv}` + `kalshi-sports-proxy-feature-packet-latest/`.

## Latest Evidence

- `make test-unit` — 481 passed, 11 deselected (was 453 after family-aware orchestration).
- Crypto characterization + macro-router regression: `pytest tests/test_kalshi_crypto_proxy_feature_packet.py tests/test_kalshi_signal_factory_status.py tests/test_kalshi_probability_breadth_scout.py tests/test_codex_macro_router.py -q` — 111 passed, unchanged.
- Binding quality gates: `make lint-baseline-check` (1413/1422 lint, 92/94 format), `tech-debt-check`, `file-sizes-check` (no new oversized files), `modularize` (2 kept/0 broken), `validate-agents` — all exit 0.
- Real public-data run `make kalshi-sports-proxy-feature-packet` — exit 0; honest status `sports_proxy_feature_packet_blocked_no_open_fast_sports_contracts` (no games in the 6h window against the current scan). Artifact is research-only (`research_only=true`, `execution_enabled=false`, `raw_payloads_copied_to_repo=false`, 0 usable rows). A wider live probe exercised the keyless fetch path and degraded KBO/LMB gracefully when ESPN returns HTTP 400.

## Artifacts

- `scripts/kalshi_sports_proxy_feature_packet.py`
- `tests/test_kalshi_sports_proxy_feature_packet.py`
- `docs/codex/macro/sports-baseball-strength-coefficients.json`
- `docs/codex/macro/latest-kalshi-sports-proxy-feature-packet.{json,md,csv}`
- `docs/codex/macro/kalshi-sports-proxy-feature-packet-latest/`
- `Makefile` (sports target)
- Raw public payloads (not committed): `/home/mrwatson/manual_drops/kalshi_sports_proxy_features/`

## Verification

| Command | Exit | Observation |
| --- | --- | --- |
| `PYTHONPATH=. .venv/bin/pytest tests/test_kalshi_sports_proxy_feature_packet.py -q` | 0 | 28 passed |
| `pytest tests/test_kalshi_crypto_proxy_*.py tests/test_kalshi_signal_factory_status.py tests/test_kalshi_probability_breadth_scout.py tests/test_codex_macro_router.py -q` | 0 | 111 passed; crypto unchanged |
| `make test-unit` | 0 | 481 passed, 11 deselected |
| `make lint-baseline-check tech-debt-check file-sizes-check modularize validate-agents` | 0 | all binding gates green; no new oversized files |
| `make kalshi-sports-proxy-feature-packet` | 0 | research-only artifact; honest `blocked_no_open` status |

## Safety

Research-only invariant preserved: every feature row carries `usable=false`, `calibrated_probability=null`, `expected_value_per_contract=null`; `research_only=true` and `execution_enabled=false` at the report level; `safety.market_execution=false`, `account_or_order_paths=false`, `database_writes=false`, `paid_calls=false`, `authenticated_api_calls=false`. Only keyless public feeds (statsapi, ESPN, Kalshi public) are used. Raw public payloads are written outside the repo under `manual_drops/` and are never committed. The strength model is fit once then frozen; the no-discretion axiom holds (no refit at decision time).

## Next Blocker

Sports observation/label loop (`scripts/kalshi_sports_proxy_observation_loop.py`) — the next sports feature (`sports-observation-label-loop`) — to snapshot ready feature rows, probe observed Kalshi tickers after game end, and match official Kalshi public settlement into label rows for downstream OOS falsification.
