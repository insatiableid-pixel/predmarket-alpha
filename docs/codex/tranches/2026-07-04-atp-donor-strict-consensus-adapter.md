# ATP Donor Strict Consensus Adapter

Date: 2026-07-04

## Objective

Move the ATP/Wimbledon sharp-provider donor rows from audit-only evidence into
the predmarket strict sports no-vig consensus chain, without promoting any row
to EV, paper sizing, or live eligibility.

## Landing

Added:

- `predmarket/sports_consensus_atp_adapter.py`
- `scripts/kalshi_sports_consensus_atp_donor_adapter.py`
- `tests/test_kalshi_sports_consensus_atp_adapter.py`
- `make kalshi-sports-consensus-atp-donor-adapter`

The adapter reads local ATP donor artifacts from `atp-oracle`:

- book JSONL: `/home/mrwatson/projects/atp-oracle/data/sports/books/the-odds-api-atp-wimbledon-sharp-20260704T234540Z.jsonl`
- Kalshi JSONL: `/home/mrwatson/projects/atp-oracle/data/sports/kalshi/kalshi-atp-wimbledon-20260704T234559Z.jsonl`

It writes derived artifacts outside the repo:

- strict consensus reference: `/home/mrwatson/manual_drops/predmarket/sports-no-vig-consensus.json`
- combined Kalshi snapshot: `/home/mrwatson/manual_drops/predmarket/sports-consensus-kalshi-snapshot.json`

The Make consensus preflight and observation loop now use the combined Kalshi
snapshot so ATP exact tickers are validated honestly against the donor Kalshi
quote rows.

## Latest Run

- ATP donor adapter: `sports_consensus_atp_donor_adapter_ready`
- ATP rows admitted to strict reference: `44`
- ATP exact Kalshi tickers: `14`
- ATP distinct providers: `4` (`pinnacle`, `betfair_exchange`, `matchbook`, `smarkets`)
- Merged strict reference rows: `108`
- Preflight: `sports_consensus_preflight_ready_with_rejected_rows`
- Valid preflight candidates: `14`, all ATP/tennis
- Rejected preflight candidates: `32` stale MLB rows with `timestamp_skew_exceeds_policy`
- Observation loop: `sports_consensus_observation_loop_ready_waiting_settlement`
- New ATP observations archived: `14`
- Falsification: `sports_consensus_falsification_blocked_insufficient_labels`
- Provider audit: `sports_consensus_provider_audit_ready_strict_anchor_present`
- Remaining provider-audit gap: `soccer_asian_sharp_not_observed`

## Guardrails

- No provider/API calls.
- No paid calls.
- No database writes.
- No account, order, execution, EV, paper stake, or live eligibility changes.
- Raw donor payloads remain in donor/manual-drop locations.
- Rows remain research-only and must still pass exact settlement labels,
  OOS/FDR, cost/spread replay, capacity, cluster, and decay gates before any
  paper or live promotion.

## Verification

```bash
python3 -m pytest -s tests/test_kalshi_sports_consensus_atp_adapter.py tests/test_kalshi_sports_consensus_provider_policy.py -q
python3 -m ruff check predmarket/sports_consensus_atp_adapter.py scripts/kalshi_sports_consensus_atp_donor_adapter.py tests/test_kalshi_sports_consensus_atp_adapter.py predmarket/sports_consensus_provider_policy.py scripts/kalshi_sports_consensus_provider_audit.py tests/test_kalshi_sports_consensus_provider_policy.py
python3 -m ruff format --check predmarket/sports_consensus_atp_adapter.py scripts/kalshi_sports_consensus_atp_donor_adapter.py tests/test_kalshi_sports_consensus_atp_adapter.py predmarket/sports_consensus_provider_policy.py scripts/kalshi_sports_consensus_provider_audit.py tests/test_kalshi_sports_consensus_provider_policy.py
make kalshi-sports-consensus-atp-donor-adapter
make kalshi-sports-consensus-preflight
make kalshi-sports-consensus-observation-loop
make kalshi-sports-consensus-falsification
python3 scripts/kalshi_sports_consensus_provider_audit.py
```

Focused tests: `11 passed`.

## Next Move

Probe exact ATP public Kalshi settlements after the observed contracts settle,
then rerun sports consensus falsification. Do not lower label/FDR thresholds.
