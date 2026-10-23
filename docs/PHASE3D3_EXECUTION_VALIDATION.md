# GoldFlow Phase 3D.3 — Execution Specification Validation

## Objective

Prevent unverified broker instrument assumptions from being mistaken for accurate cash P&L or executable risk. This phase does not change or optimize the SMC signal hypothesis. Its purpose is to improve auditability of contract-size, point-size, lot constraints, tick size/value, currency assumptions, symbol identity, and broker-server identity.

## Current data status

The bundled datasets currently produce `ASSUMPTIONS_ONLY` from `scripts/audit_execution_specs.py`. Their sidecars declare MT5 origin and timestamp processing, but do not contain a complete captured `MT5.symbol_info` specification. Backtests can still be run for exploratory diagnostics; full-history, common-window, lifecycle, and holdout artifacts embed the spec-audit state and print a prominent warning. Strict execution-spec mode refuses to run unless all required instrument fields match the active `BacktestConfig`, XAU/USD/USD currency assumptions are captured, tick-value arithmetic is consistent, and symbol/server labels agree.

This does **not** authenticate historical feed provenance. Even after the specification audit matches, independent broker/source provenance, tick-level execution behavior, and a genuinely untouched forward period remain unverified.

## Capture specifications on the machine that runs MT5

1. Open the intended MetaTrader 5 desktop terminal and log into the same broker/server from which the historical bars were downloaded.
2. From the project root, run:

   ```powershell
   python scripts/capture_mt5_execution_specs.py --symbol XAUUSD
   ```

3. The script uses the terminal's actual `symbol_info` response and updates only matching `*_clean.meta.json` sidecars. It does not change OHLC CSV files. It refuses synthetic datasets, symbol aliases, missing broker identity, and known server mismatches.
4. Review `reports/execution_spec_audit.md` and `reports/execution_spec_audit.json`. Fix a configuration mismatch deliberately; do not override it silently.
5. If the broker calls the instrument `XAUUSD.a`, `GOLD`, or another alias while the saved dataset is labeled `XAUUSD`, do not attach specifications automatically. Re-ingest the historical bars under the actual instrument symbol or perform a separate documented equivalence investigation.

## Run modes

Exploratory run (allowed with a warning when specs are missing):

```powershell
python scripts/run_smc_backtest.py --timeframes H4 H1 M15 M5
```

Strict run (recommended after capture and config reconciliation):

```powershell
python scripts/run_smc_backtest.py --timeframes H4 H1 M15 M5 --require-matched-execution-spec
```

If a broker's values differ from the defaults, set `--contract-size-oz`, `--point-size`, `--min-lot`, `--lot-step`, and `--max-lots` to the observed values; also set commission and spread assumptions intentionally. For a strict run, those values must match the sidecar audit. The current simulator assumes XAU as the base, USD as the symbol profit currency, and USD as the account/P&L currency. It cross-checks `trade_tick_value` against `trade_contract_size × trade_tick_size` with a 5% tolerance when these conditions hold. The Streamlit Backtesting page exposes the same principal configuration fields and defaults to requiring a match.

## Status meanings

- `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE`: required captured instrument fields match the active configuration; historical data authenticity remains unverified.
- `ASSUMPTIONS_ONLY`: required fields are missing or incomplete.
- `CONFIG_MISMATCH`: captured values differ from the active config.
- `SYMBOL_MISMATCH` / `SYMBOL_UNVERIFIED`: dataset symbol and captured instrument identity disagree or cannot be checked.
- `BROKER_MISMATCH` / `BROKER_UNVERIFIED`: dataset and captured broker-server identity disagree or cannot be checked.
- `CURRENCY_UNSUPPORTED` / `CURRENCY_UNVERIFIED`: the USD-valued engine cannot confirm XAU base currency, USD profit currency, and USD account currency.
- `TICK_VALUE_MISMATCH`: MT5 tick value differs by more than 5% from `trade_contract_size × trade_tick_size` under XAU/USD assumptions and an allowlisted calculation mode.
- `CALC_MODE_UNSUPPORTED`: captured calculation mode is not allowlisted for the current contract-size P&L formula.
- `CALC_MODE_UNVERIFIED`: calculation mode or its active-MT5 symbolic mapping is absent, malformed, fractional, or otherwise unusable.
- `CALC_MODE_MISMATCH`: numeric `trade_calc_mode` disagrees with the symbolic name/code mapping captured from the active MetaTrader5 package.

## Tests and acceptance criteria

The test suite covers missing/nonpositive/malformed fields, configuration mismatches, symbol/server identity mismatch, strict-gate refusal, sidecar-only writes, synthetic-data refusal, and rollback if a later sidecar write fails. Acceptance does not depend on improving win rate or P&L. A strict-gate pass is an execution-assumption check, not a strategy-performance verdict.

## Current milestone verification record (2026-10-20)

- Full unit/regression suite at the Phase 3D.3 baseline: **293 passed**.
- Follow-up remediation for independent audit findings: **304 passed** (see `reports/PHASE3D3_ANTIGRAVITY_REMEDIATION.md`).
- `compileall` across `src`, `pages`, `scripts`, `tests`, and `app.py`: passed.
- Readiness audit: `READY_WITH_WARNINGS`, no critical blockers.
- Current processed-data execution-spec audit: `ASSUMPTIONS_ONLY`, expected because the four existing data sidecars do not include a real `MT5.symbol_info` capture.
- Exploratory M5 CLI path was exercised successfully with the warning present; strict mode was exercised and refused to run before simulation as designed.
- The latest audit snapshot has been embedded into full-history, common-window, lifecycle, and holdout metric JSON files. This refresh changes audit metadata only; it does not alter reported trade calculations.

The final full-suite run also caught and fixed a diagnostic-priority issue: a direct point/contract configuration mismatch now takes precedence over secondary tick-value arithmetic mismatch in the summary status, while the detailed `tick_value_check` remains present. That ensures the primary actionable discrepancy is shown first.


## Follow-up correctness remediation (2026-10-20)

Antigravity's independent review identified a possible partial metadata update if a write failed after earlier sidecars had already been updated, several malformed-value test gaps, and a `digits=0` boundary case. The follow-up patch stages byte-exact same-filesystem backups before mutation and restores attempted sidecars on a later write failure. If rollback itself fails, the utility raises an explicit error naming the affected paths and preserves the original backup for manual recovery rather than silently deleting it. The audit reports `wrong_type_fields` separately from `missing_required_fields`, rejects `digits < 1`, and allowlists only the MT5 calculation modes whose documented profit formula is linear in contract size. Futures/tick-price, bond, collateral, unknown, and malformed modes are blocked from strict validation. This formula allowlist does not authenticate the broker or history source.

Verification after the patch: `python -m pytest tests/ -q` — **304 passed**; `python -m compileall -q src pages scripts tests app.py` — passed. The data audit remains `ASSUMPTIONS_ONLY` (exit code 2, expected) because the bundled sidecars still lack captured live MT5 specifications. The full SMC signal and holding-period parameters remain unchanged.


## Calculation-mode enum source hardening (2026-10-20)

The capture path must not guess enum numeric IDs. It resolves the mode name using constants exported by the active MetaTrader5 Python package, stores the constant map in the metadata sidecar, and the audit checks that the reported numeric mode matches the captured name/code pair. An empty map, ambiguous code, or unresolved name prevents `captured_complete`; absent symbol info remains `unavailable`. Unsupported, unverified, and mismatched modes block strict execution. Official profit formulas by calculation mode are documented in the [MQL5 symbol properties reference](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants).


Latest verification after dynamic mode resolution (2026-10-20): **327 passed**, compile check passed, readiness `READY_WITH_WARNINGS`, data execution-spec audit `ASSUMPTIONS_ONLY`, and strict backtesting correctly refused before execution. All five metric audit snapshots were refreshed and checked for trade/config invariance against the Phase 3D.3.1 package.
