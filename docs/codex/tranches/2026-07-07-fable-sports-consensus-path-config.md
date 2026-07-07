# 2026-07-07 Fable Sports Consensus Path Config

## Purpose

Continue Fable's path/config cleanup on the sharp no-vig sports consensus lane.
The Makefile roots were configurable, but several sports-consensus scripts still
had workstation-specific default paths in source.

## Changes

- `scripts/kalshi_sports_consensus_preflight.py` now uses
  `manual_drop_path("predmarket", "sports-no-vig-consensus.json")`.
- Consensus observation and falsification default archive directories now use
  `manual_drop_path()`.
- ATP/NFL/NBA/soccer strict consensus adapters now derive default reference,
  combined Kalshi snapshot, current Kalshi snapshot, and ATP donor file paths
  from `manual_drop_path()` / `project_path()`.
- Provider audit and soccer Asian provider diagnostic defaults now use
  configurable path helpers.
- Added a regression test scanning all `scripts/kalshi_sports_consensus_*.py`
  files for `/home/mrwatson/manual_drops` or `/home/mrwatson/projects`.

## Compatibility

All CLI flags and Make variables are preserved. Existing workstation defaults
still resolve through `Path.home()`, but the scripts are no longer pinned to a
single username.

## Guardrails

- No thresholds changed.
- No labels inferred.
- No candidate promotion.
- No EV/paper/live behavior change.
- No account/order/live execution path touched.

## Verification

- `python -m pytest tests/test_kalshi_path_defaults.py -q`
- `ruff check scripts/kalshi_sports_consensus_preflight.py scripts/kalshi_sports_consensus_observation_loop.py scripts/kalshi_sports_consensus_falsification.py scripts/kalshi_sports_consensus_atp_donor_adapter.py scripts/kalshi_sports_consensus_nfl_adapter.py scripts/kalshi_sports_consensus_soccer_adapter.py scripts/kalshi_sports_consensus_nba_adapter.py scripts/kalshi_sports_consensus_provider_audit.py scripts/kalshi_sports_consensus_soccer_asian_provider_diagnostic.py tests/test_kalshi_path_defaults.py`
- `make kalshi-sports-consensus-preflight`
- `make kalshi-sports-consensus-provider-audit`

Result: focused tests pass; Ruff clean; representative targets exit `0`.
