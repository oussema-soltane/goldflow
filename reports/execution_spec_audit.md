# GoldFlow — Broker Execution Specification Audit

**Generated (UTC):** 2026-10-22T09:39:19.289370+00:00
**Overall status:** MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE

This preflight compares current BacktestConfig defaults with instrument metadata captured from `MT5.symbol_info`. It does not verify that the historical price data is authentic, and it does not certify execution quality.

## Assumptions Under Audit

| Engine setting | Current default | MT5 metadata field |
|---|---:|---|
| `point_size` | 0.01 | `point` |
| `contract_size_oz` | 100.0 | `trade_contract_size` |
| `min_lot` | 0.01 | `volume_min` |
| `lot_step` | 0.01 | `volume_step` |
| `max_lots` | 100.0 | `volume_max` |
| `trade_calc_mode` | documented linear contract-size profit formula required | `trade_calc_mode` |

## Dataset Results

| Symbol | Timeframe | Spec capture status | Calculation mode | Formula compatibility | Audit result | Missing required fields | Wrong-type fields | Mismatches |
|---|---|---|---|---|---|---|---|---|
| XAUUSD | H1 | captured_complete | SYMBOL_CALC_MODE_CFDLEVERAGE (4) | supported_linear_contract_size_formula | MATCHED_CAPTURED_DEFAULTS | None | None | tick value 0.1 reconciled to 1.0 via order_calc_profit |
| XAUUSD | H4 | captured_complete | SYMBOL_CALC_MODE_CFDLEVERAGE (4) | supported_linear_contract_size_formula | MATCHED_CAPTURED_DEFAULTS | None | None | tick value 0.1 reconciled to 1.0 via order_calc_profit |
| XAUUSD | M15 | captured_complete | SYMBOL_CALC_MODE_CFDLEVERAGE (4) | supported_linear_contract_size_formula | MATCHED_CAPTURED_DEFAULTS | None | None | tick value 0.1 reconciled to 1.0 via order_calc_profit |
| XAUUSD | M5 | captured_complete | SYMBOL_CALC_MODE_CFDLEVERAGE (4) | supported_linear_contract_size_formula | MATCHED_CAPTURED_DEFAULTS | None | None | tick value 0.1 reconciled to 1.0 via order_calc_profit |

## Cross-Dataset Specification Matching

- **Status:** consistent
- **Datasets checked:** 4
- **Essential fields verified identical:** `digits`, `point`, `trade_contract_size`, `trade_tick_size`, `volume_min`, `volume_step`, `volume_max`, `trade_calc_mode`, `currency_base`, `currency_profit`, `account_currency`
- **Permitted varying observational fields:** `captured_at_utc`, `spread`, `spread_float`, `trade_stops_level`, `trade_freeze_level`
- **Result:** All active datasets share identical essential calculation specifications.

## Reconciled Discrepancies and Empirical Inquiries

- **Reconciled field:** trade_tick_value (reported 0.1, reconciled to 1.0 via order_calc_profit)
- **Warning note:** TICK_VALUE_RECONCILED: symbol_info.trade_tick_value (0.1) differs from contract formula (1.0), but MT5 order_calc_profit empirically confirmed 1.00 USD/tick for 1.0 lot across BUY and SELL.

## Interpretation

- `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE` means the captured required fields equal current defaults; it is not broker or data-source authentication.
- `ASSUMPTIONS_ONLY` means at least one dataset has no complete instrument-specification record. Do not infer point size or contract size from OHLC decimals; refresh data from the intended MT5 terminal to capture the actual fields.
- `CONFIG_MISMATCH` means at least one configured default differs from the captured broker field. Update the research config deliberately and rerun the audit; do not silently overwrite either value.
- `SYMBOL_MISMATCH`, `SYMBOL_UNVERIFIED`, `BROKER_MISMATCH`, and `BROKER_UNVERIFIED` fail strict execution-spec validation. Re-ingest from the intended terminal rather than attach an unrelated symbol/server specification.
- `CURRENCY_UNSUPPORTED` / `CURRENCY_UNVERIFIED` means the USD-valued position and P&L assumptions cannot be reconciled to the captured base/profit/account currencies.
- `TICK_VALUE_MISMATCH` means MT5's captured tick value differs by more than 5% from `trade_contract_size × trade_tick_size` under XAU/USD assumptions without verified empirical order_calc_profit reconciliation.
- `CROSS_DATASET_SPEC_MISMATCH` means different timeframe datasets have conflicting essential calculation specifications (e.g. different contract sizes or calculation modes).
- `CALC_MODE_UNSUPPORTED` means the captured mode is not allowlisted for this simulator's contract-size P&L formula. `CALC_MODE_UNVERIFIED` means the mode or the active MT5 symbolic-constant map is missing/malformed. `CALC_MODE_MISMATCH` means the captured numeric enum code disagrees with the name/code mapping captured from the active MT5 package. All three block strict runs.
- The allowlist includes the documented linear profit formula modes FOREX, FOREX_NO_LEVERAGE, CFD, CFDINDEX, CFDLEVERAGE, EXCH_STOCKS, and EXCH_STOCKS_MOEX. Futures/tick-price, bonds, collateral, and unknown modes are not accepted by this engine formula. Official formula reference: https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants.
- `wrong_type_fields` identifies required numeric values that are present but unusable (for example boolean, NaN, infinity, or malformed values). These also remain in `missing_required_fields` for strict-gate compatibility.

## Required fields

`point`, `trade_contract_size`, `volume_min`, `volume_step`, `volume_max`, `digits`, `trade_tick_size`, `trade_tick_value`, `trade_calc_mode`, `trade_calc_mode_name`, `trade_calc_mode_name_source`, `trade_calc_mode_constant_values`

## Required currency fields

`currency_base=XAU`, `currency_profit=USD`, `account_currency=USD`

## Errors

- None

**Caveat:** Matching instrument specifications and server labels do not independently authenticate that the OHLC history came from the named broker/feed.
