# Soccer Asian Provider Auto-Probe

Date: 2026-07-07

## Why

Fable's sports consensus requirement treats World Cup/soccer as immature until an Asian sharp anchor such as SBOBet, Singbet, or IBC is present. The diagnostic could previously report `soccer_asian_provider_diagnostic_blocked_target_books_not_requested` when recent local soccer source files existed but did not include an explicit target-provider request. That left an avoidable ambiguity: was soccer blocked because the target books were unavailable, or because the normal evidence path never asked for them?

## What Changed

- Added `--capture-current-if-needed` to `scripts/kalshi_sports_consensus_soccer_asian_provider_diagnostic.py`.
- The helper reuses local soccer files when they already requested or observed target Asian providers.
- If no local target-provider request exists and a configured Odds API key file is present, the helper performs the bounded current target-book probe.
- Wired the default `make kalshi-sports-consensus-soccer-asian-provider-diagnostic` path to use `--capture-current-if-needed`.
- Added tests proving auto-capture fires only when target books were not previously requested.

## Real State

Real default run:

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-consensus-soccer-asian-provider-diagnostic
```

Result:

- status: `soccer_asian_provider_diagnostic_blocked_target_books_unavailable_in_feed`
- requested target providers: `3` (`ibc`, `sbobet`, `singbet`)
- observed target providers: `0`
- missing target providers: `3`
- source files: `20`
- soccer events: `104`
- quota remaining: `301`

Interpretation: the soccer blocker is now a genuine external/provider-availability blocker for the current legal feed, not a local orchestration gap.

## Guardrails

- No Asian sharp maturity downgrade.
- No non-Asian exchange rows treated as a substitute for the target providers.
- No labels inferred.
- No probability, EV, paper stake, or live eligibility changed.
- No account, order, or execution path touched.

## Verification

```bash
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp .venv/bin/python -m pytest tests/test_kalshi_sports_consensus_soccer_asian_provider.py -q
.venv/bin/ruff check scripts/kalshi_sports_consensus_soccer_asian_provider_diagnostic.py tests/test_kalshi_sports_consensus_soccer_asian_provider.py
.venv/bin/python -m py_compile scripts/kalshi_sports_consensus_soccer_asian_provider_diagnostic.py predmarket/sports_consensus_soccer_asian_provider.py
PYTHONPATH=. TMPDIR=/tmp TMP=/tmp TEMP=/tmp make kalshi-sports-consensus-soccer-asian-provider-diagnostic
```

Results:

- focused tests: `6 passed`
- Ruff: pass
- py-compile: pass
- default Make target: exit `0`
