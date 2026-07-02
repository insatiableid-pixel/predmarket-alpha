# Type 2 Candidate Disposition: type2-candidate-disposition-latest

## Scope

- Mode: review-only
- Research only: true
- Execution enabled: false
- Status: `candidate_disposition_watch_only`
- Timing policy: `sportsbook_and_kalshi_captures_must_be_strictly_before_commence_time`

## Summary

- Candidates checked: 52
- Original pass/watch: 0 / 52
- Kept review candidates: 0
- Watch only: 48
- Downgraded timing mismatches: 4
- Manual timing checks needed: 0

## Kept Review Candidates

No rows survived the timing policy as review candidates.
## Downgraded Timing Mismatches

- `KXMLBGAME-26JUN291835CWSBAL-CWS`: At least one snapshot was captured at or after first pitch. (first pitch `2026-06-29T22:36:00Z`)
- `KXMLBGAME-26JUN291835CWSBAL-BAL`: At least one snapshot was captured at or after first pitch. (first pitch `2026-06-29T22:36:00Z`)
- `KXMLBGAME-26JUN291840PITPHI-PIT`: At least one snapshot was captured at or after first pitch. (first pitch `2026-06-29T22:41:00Z`)
- `KXMLBGAME-26JUN291840PITPHI-PHI`: At least one snapshot was captured at or after first pitch. (first pitch `2026-06-29T22:41:00Z`)

## Guardrail

This report only narrows rows for manual research review. It does not authorize execution or account activity.
