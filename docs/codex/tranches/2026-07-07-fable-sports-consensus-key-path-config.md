# 2026-07-07 Fable Sports Consensus Key Path Config

## Landing

Removed the hardcoded Windows/OneDrive Odds API key-file path from the sports consensus reference stack.

The default key-file path is now:

- `PREDMARKET_MANUAL_DROPS_ROOT/secrets/the_odds_api_key.txt` from Makefile.
- `manual_drop_path("secrets", "the_odds_api_key.txt")` in Python.
- `KALSHI_SPORTS_CONSENSUS_KEY_FILE` or `THE_ODDS_API_KEY_FILE` can override the Python default.

This keeps provider credentials outside the repo while avoiding a machine-specific path in source.

## Local Path Check

I checked path existence only, without reading key contents:

- New default: `$HOME/manual_drops/secrets/the_odds_api_key.txt` did not exist.
- Old hardcoded path: `/mnt/c/Users/mrwat/OneDrive/Desktop/Welcome to The Odds API!.txt` did not exist from WSL.

Provider capture still requires a configured key file before live pulls.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No sportsbook-derived settlement labels introduced.
- No manual EV, paper, or live promotion occurred.
- No account, order, or execution path was touched.

## Verification

- `python -m pytest tests/test_kalshi_path_defaults.py tests/test_kalshi_sports_consensus_reference_builder.py -q` -> `23 passed`
- `ruff check predmarket/sports_consensus_reference_builder.py tests/test_kalshi_path_defaults.py` -> pass
- `make lint-baseline-check` -> pass (`lint 98/1422`, `format 17/94`)
- `python -m py_compile predmarket/sports_consensus_reference_builder.py` -> pass
- `make -n kalshi-sports-consensus-refresh` -> pass
- `make -n kalshi-sports-consensus-sharp-provider-capture` -> pass
- `make -n kalshi-sports-consensus-nfl-adapter` -> pass
