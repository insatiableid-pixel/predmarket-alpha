# Kalshi Sports Proxy Feature Packet

Date: 2026-07-03

## Outcome

- Built the baseball feature-packet builder `scripts/kalshi_sports_proxy_feature_packet.py` (the sports analog of the crypto feature packet), reusing the crypto scaffolding (report envelope, `safe_research_artifact`, `safety_flags`, `build_gates`, `write_*` + `latest-*` pointers, close-time-windowed selection).
- Added the sports-specific plug-in: (1) per-league team-identity resolver mapping Kalshi team codes (`CWSBAL`, `KTWHAN`, `LDYPDP`, ...) to external game/team IDs (MLB Stats API `gamePk` + team ids; ESPN event/competitor ids for KBO/LMB); (2) a keyless feature fetcher (statsapi schedule + standings for MLB, ESPN scoreboard for KBO/LMB) with injectable `fetch_json`; (3) a pre-game strength model (standings win% + pythagorean -> sigmoid win probability) with coefficients fit once then FROZEN in a checked-in artifact; (4) a mechanical `|p_win - yes_ask| >= tau` prediction rule.
- Regression guard against the prior run-line sign-convention bug: game-winner series only (`KXMLBGAME/KXKBOGAME/KXLMBGAME`); `KXMLBRUN-*` and player props are rejected by construction; YES is interpreted as "selected team wins the game outright" (moneyline), never a margin.
- Added Make target `kalshi-sports-proxy-feature-packet` and the frozen-coefficient artifact `docs/codex/macro/sports-baseball-strength-coefficients.json`.
- Raw public payloads (statsapi/ESPN) written outside the repo under `manual_drops/kalshi_sports_proxy_features/`; derived artifacts + `latest-*` pointers under `docs/codex/macro/`.

## Evidence

- `make test-unit` 481 passed (was 453 after family-aware orchestration; +28 sports feature-packet artifact-replay tests).
- Crypto characterization + router suite unchanged: 111 passed.
- All 5 binding quality gates green (`lint-baseline-check` 1413/1422, `tech-debt-check`, `file-sizes-check` no new oversized files, `modularize` 2 kept/0 broken, `validate-agents`).
- `make kalshi-sports-proxy-feature-packet` exits 0; latest artifact is research-only (`research_only=true`, `execution_enabled=false`, every row `usable=false`/`calibrated_probability=null`, raw payloads outside repo). Honest status `sports_proxy_feature_packet_blocked_no_open_fast_sports_contracts` (no games in the 6h window against the current scan); a wider live-data probe exercised the keyless statsapi/ESPN fetch path and degraded KBO/LMB gracefully when ESPN returns 400.

## Learned

- Kalshi MLB team codes coincide with statsapi standings abbreviations (Arizona is `AZ` in both, NOT `ARI`); 2-letter codes (`SF`,`TB`,`KC`) make the team-suffix decomposition variable-length, handled by a reverse-split against the per-league code set.
- The contract ticker carries a `-SELECTED` side suffix whose win resolves YES (moneyline); `p(yes) = p_home_win` when the selected team is home, else `1 - p_home_win`.
- ESPN KBO/LMB scoreboard endpoints currently return HTTP 400 (off-season/slug drift); the feature packet degrades those leagues to `proxy_source_unavailable` rather than crashing. MLB Stats API (schedule + standings on `statsapi.mlb.com`) is the solid, keyless strength source.

## Next Route

Sports feature packet is built; the next sports milestone is the observation/label loop (`scripts/kalshi_sports_proxy_observation_loop.py`) to snapshot ready rows and match Kalshi public settlement for OOS falsification labels.

## Guardrail

Stop before treating statsapi/ESPN proxy feeds as official settlement labels, computing usable EV, sizing, execution, or account/order paths. Every row stays `usable=false` and `calibrated_probability=null` until falsified + calibrated by a passing gate.
