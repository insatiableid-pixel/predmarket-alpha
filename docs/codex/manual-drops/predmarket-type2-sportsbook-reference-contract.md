# Predmarket Type 2 Sportsbook Reference Contract

## Purpose

This file defines the small local JSON reference needed before predmarket can compare Kalshi paper markets against sportsbook prices.

The reference is a derived handoff file. It is not a raw provider dump.

## Where To Put It

Preferred location outside the repo:

`/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json`

If a temporary fixture is needed for tests, keep it under `/tmp` or a test temp directory. Do not copy raw provider responses into this repository.

## Required Shape

```json
{
  "schema_version": 1,
  "created_at_utc": "2026-06-28T00:00:00Z",
  "source_note": "Small manual sportsbook reference, derived from local observation.",
  "markets": [
    {
      "reference_id": "short-stable-id",
      "kalshi_ticker": "KXMLBPROP-26JUN27-JUDGEHIT",
      "sportsbook": "manual-reference",
      "market_label": "Aaron Judge over 0.5 hits",
      "capture_time_utc": "2026-06-28T00:00:00Z",
      "yes": { "american": -110 },
      "no": { "american": -110 }
    }
  ]
}
```

## Required Fields

- `markets`: non-empty list.
- `reference_id`: stable local row identifier.
- `kalshi_ticker`: exact ticker from the local Kalshi scored/refined artifact.
- `yes` and `no`: two-sided odds payloads.

Supported odds payloads:

```json
{ "american": -110 }
{ "decimal": 1.91 }
{ "implied_probability": 0.524 }
```

## Rules

- Use exact `kalshi_ticker` only.
- Do not rely on title, team-name, player-name, or fuzzy matching.
- Include only the small derived rows needed for comparison.
- Do not include keys, tokens, cookies, account identifiers, order identifiers, or raw provider payloads.
- Do not include execution instructions.
- A passing preflight only means the file can be used by the paper matcher for manual review.

## No-Provider Command Sequence

```bash
cd /home/mrwatson/projects/predmarket-alpha
make type2-reference-preflight TYPE2_SPORTSBOOK_JSON=/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json
make type2-paper-matcher TYPE2_SPORTSBOOK_JSON=/home/mrwatson/manual_drops/predmarket/type2-sportsbook-reference.json
make macro-status
python3 scripts/codex_macro_router.py route --write
```

Stop if the preflight does not report `reference_ready`.
