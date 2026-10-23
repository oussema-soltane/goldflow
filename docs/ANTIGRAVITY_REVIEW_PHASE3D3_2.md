# Antigravity Independent Review — Phase 3D.3.2 Calculation-Mode Guard

## Review objective

Independently review GoldFlow's new `trade_calc_mode` formula allowlist and the refreshed audit snapshots. Do not modify SMC entry/exit rules, holding-period settings, backtest engine trade logic, or historical P&L metrics.

## Scope

- `src/research/execution_spec_audit.py`
- `src/data/loader.py`
- `scripts/audit_execution_specs.py`
- `tests/test_execution_spec_audit.py`
- `tests/test_mt5_data_pipeline.py`
- `tests/test_capture_mt5_execution_specs.py`
- `reports/execution_spec_audit.json` / `.md`
- The five `reports/*metrics*.json` files that embed the current audit snapshot

## Required independent checks

1. Confirm the allowlisted calc-mode names have documented profit formula `(close - open) * Contract_Size * Lots` under the official MQL5 reference. No enum IDs may be hard-coded: capture must resolve the symbolic name from the active MetaTrader5 package constants and retain the captured name→numeric map so the audit can validate code/name consistency.
2. Confirm futures/tick-price, exchange futures, bond, collateral, unknown and malformed modes block strict validation.
3. Confirm tick-value arithmetic is not performed for missing/unsupported calc modes and that it is only evaluated under XAU/USD/USD currency assumptions with positive finite inputs.
4. Confirm `trade_calc_mode`, a uniquely resolved symbolic name/source, and a non-empty active-package constant map are required by the audit and by `captured_complete` classification; missing values/constants must be incomplete or unavailable (as appropriate) and block strict runs.
5. Confirm direct config mismatch has priority over derived tick-value mismatch and diagnostic details remain available.
6. Confirm every strict path still refuses when the audit's overall status is not `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE`.
7. Confirm that the five metrics JSON audit snapshots match `reports/execution_spec_audit.json` and that every trade metric remains unchanged from the preceding Phase 3D.3.1 report.
8. Re-run the full test suite and compile check, and inspect the diff to prove no signal or backtest execution parameters changed.

## Reproduction commands

```powershell
py -3.13 -m pytest tests/ -q
py -3.13 -m compileall -q src pages scripts tests app.py
py -3.13 scripts/research_readiness.py
py -3.13 scripts/audit_execution_specs.py
py -3.13 scripts/run_smc_backtest.py --timeframes M5 --require-matched-execution-spec
```

Expected with the currently bundled data: tests pass; compilation passes; readiness is `READY_WITH_WARNINGS`; specification audit is `ASSUMPTIONS_ONLY` (exit 2); and strict backtesting refuses before execution. This is expected because no live `MT5.symbol_info` specification has been captured in the current workspace. Also run focused tests for: missing symbol info despite module constants being present; empty enum-constant map; non-unique enum-code mappings; captured numeric code/name disagreement; and no tick arithmetic for unverified modes.

## Review output format

Report each finding with severity, file/line, reproducible evidence, and proposed regression test. Separate simulator correctness from strategy performance. Do not claim a win-rate improvement, strategy edge, or independent feed authentication.

Official formula reference: https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants
