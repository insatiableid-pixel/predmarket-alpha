# Type 2 Reference Intake Preflight: type2-reference-preflight-latest

## Scope

- Mode: review-only
- Research only: true
- Execution enabled: false
- Ready: `true`
- Status: `reference_ready`
- Matching policy: `explicit_kalshi_ticker_only`

## Summary

- References: 52
- Valid references: 52
- Missing tickers: 0
- Unknown tickers: 0
- Invalid odds rows: 0
- Blockers: 0

## Gates

- `research_only_safety`: `pass` - No provider, paid, database, account, order, or execution calls are used.
- `reference_file_available`: `pass` - Sportsbook reference JSON supplied.
- `reference_rows_present`: `pass` - Reference rows: 52.
- `explicit_kalshi_mappings`: `pass` - Every reference row has kalshi_ticker.
- `kalshi_tickers_resolve`: `pass` - All mapped tickers resolve to the local Kalshi artifact.
- `two_sided_odds_valid`: `pass` - Every mapped row has usable two-sided YES/NO odds.
- `no_fuzzy_matching`: `pass` - Only exact kalshi_ticker mappings are allowed.

## References

### kxmlbgame-26jun291835cwsbal-cws-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291835CWSBAL-CWS`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291835cwsbal-bal-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291835CWSBAL-BAL`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291840pitphi-pit-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291840PITPHI-PIT`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291840pitphi-phi-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291840PITPHI-PHI`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291905detnyy-det-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291905DETNYY-DET`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291905detnyy-nyy-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291905DETNYY-NYY`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291907nymtor-nym-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291907NYMTOR-NYM`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291907nymtor-tor-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291907NYMTOR-TOR`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291910wshbos-wsh-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291910WSHBOS-WSH`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291910wshbos-bos-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291910WSHBOS-BOS`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291910texcle-tex-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291910TEXCLE-TEX`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291910texcle-cle-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291910TEXCLE-CLE`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291940cinmil-cin-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291940CINMIL-CIN`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun291940cinmil-mil-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN291940CINMIL-MIL`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292005sdchc-sd-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292005SDCHC-SD`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292005sdchc-chc-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292005SDCHC-CHC`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292010minhou-min-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292010MINHOU-MIN`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292010minhou-hou-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292010MINHOU-HOU`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292040miacol-mia-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292040MIACOL-MIA`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292040miacol-col-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292040MIACOL-COL`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292140ladath-lad-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292140LADATH-LAD`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292140ladath-ath-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292140LADATH-ATH`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292140laasea-laa-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292140LAASEA-LAA`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun292140laasea-sea-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN292140LAASEA-SEA`
- Valid: `true`
- Blockers: []

### kxmlbgame-26jun301835cwsbal-cws-fanduel

- Kalshi ticker: `KXMLBGAME-26JUN301835CWSBAL-CWS`
- Valid: `true`
- Blockers: []


## Guardrail

A ready preflight only means the local reference can be used by the paper matcher for manual review.
