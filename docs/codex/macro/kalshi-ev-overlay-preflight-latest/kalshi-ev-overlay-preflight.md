# Kalshi EV Overlay Preflight

- Status: `overlay_preflight_usable_ev_rows_present`
- Research only: `true`
- Contract-mapping files: `1`
- Probability files: `1`
- Valid contract-mapping rows: `32`
- Valid calibrated-probability rows: `32`
- Exact joins: `32`
- Overlay EV rows: `32`
- Usable overlay EV rows: `12`

## Gates

| Gate | Status | Reasons |
| --- | --- | --- |
| `contract_mapping_files_present` | `pass` | Found 1 contract-mapping overlay file(s). |
| `calibrated_probability_files_present` | `pass` | Found 1 calibrated-probability overlay file(s). |
| `valid_contract_mapping_rows_present` | `pass` | Loaded 32 valid contract-mapping row(s). |
| `valid_calibrated_probability_rows_present` | `pass` | Loaded 32 valid calibrated-probability row(s). |
| `exact_ticker_side_join_present` | `pass` | Found 32 exact contract_ticker/side join(s). |
| `usable_overlay_ev_rows_present` | `pass` | Found 12 usable overlay EV row(s). |

## Next Action

Review the usable overlay EV rows in the ledger; execution remains disabled.
