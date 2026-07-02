# Kalshi Probability Breadth Scout

Built the first source-readiness scout for the "signal breadth over depth" lane. It reads the public Kalshi universe scan, identifies fast-settling market families, probes public crypto proxy feeds, and records the official-settlement-source gap without claiming EV.

## Outputs
- `scripts/kalshi_probability_breadth_scout.py`
- `tests/test_kalshi_probability_breadth_scout.py`
- `docs/codex/macro/latest-kalshi-probability-breadth-scout.json`
- `docs/codex/macro/latest-kalshi-probability-breadth-scout.md`
- `docs/codex/macro/latest-kalshi-probability-breadth-scout-candidates.csv`

## Result
The scout selected `crypto_proxy_fast_label_route`.

Latest counts:
- 6,764 universe candidates in the 72-hour scan.
- 1,538 candidates close within 6 hours.
- 1,256 of those are finance/crypto.
- 1,239 finance/crypto candidates close within 1 hour.
- 4 public proxy sources were reachable.

Raw public proxy snapshot:
`/home/mrwatson/manual_drops/kalshi_probability_sources/crypto_proxy_probe_20260702T001803Z.json`

## Guardrail
Kalshi crypto contracts settle from CF Benchmarks RTI. Coinbase/Kraken data is only a proxy feature source, not an official settlement label, calibrated probability, EV claim, or execution signal.

## Router State
`make macro-route` now recommends predmarket with status `signal_factory_probability_breadth_scout_ready_crypto_proxy_route`.

Next tranche:
build contract-keyed crypto proxy feature packets for fast-settling Kalshi crypto contracts, while preserving CF Benchmarks RTI as the official settlement source.
