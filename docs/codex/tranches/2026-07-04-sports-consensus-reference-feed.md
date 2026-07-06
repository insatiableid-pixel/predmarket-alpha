# Sports Consensus Reference Feed

Date: 2026-07-04

## Landing

Built the missing timestamp-matched multi-book sports consensus feed that the
sports no-vig preflight was waiting on.

New code:

- `predmarket/sports_consensus_reference_builder.py`
- `scripts/kalshi_sports_consensus_reference_build.py`
- `make kalshi-sports-consensus-reference-build`
- `make kalshi-sports-consensus-refresh`

The builder adapts the useful odds-surveillance-platform pattern without making
that repo a runtime dependency: use a configured book set, enforce source-age
limits, keep raw provider payloads outside this repo, emit only a derived
reference file, and require exact Kalshi ticker mapping before preflight.

Current operational default is MLB h2h game-winner consensus from
`lowvig,betonlineag`. The derived reference is written to:

`/home/mrwatson/manual_drops/predmarket/sports-no-vig-consensus.json`

Raw current odds captures stay outside the repo under:

`/home/mrwatson/manual_drops/odds_api/`

## Latest Run

Command:

```bash
make kalshi-sports-consensus-refresh
make kalshi-sports-evidence-cycle
```

Results:

- Consensus reference build: `sports_consensus_reference_built_with_warnings`
- Reference rows: `44`
- Unique Kalshi tickers: `22`
- Distinct books: `2`
- Skipped events: `3`
- Consensus preflight: `sports_consensus_preflight_ready`
- Valid consensus candidates: `22`
- Consensus blockers: `0`
- Sports evidence cycle: `sports_evidence_cycle_ready_with_label_progress`
- Sports surfaces: `5`
- Sports consensus valid candidates surfaced in cycle: `22`
- Live preflight: `kalshi_live_blocked`

## Guardrails

- No account/order paths.
- No live execution.
- API key was not printed.
- Raw provider payloads were not copied into the repo.
- The consensus feed only admits configured-book rows with exact Kalshi ticker
  mappings.
- Consensus rows are not live-tradable by existence; they still need OOS/FDR,
  cost, capacity, cluster, and decay gates before any paper stake.

## Next

Promote this consensus surface from preflight inventory into its own falsification
ledger: track Kalshi-vs-consensus divergence by exact ticker, settle outcomes,
test OOS/FDR by sport/market/price bucket, and only then allow paper sizing.
