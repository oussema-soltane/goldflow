# GoldFlow Phase 3D.3.2 — Calculation-Mode Formula Guard

**Date:** 2026-10-20  
**Scope:** execution-specification preflight, capture completeness, diagnostics, and report metadata only. No SMC signal, target, stop, holding-period, backtest fill, or trade-selection logic was changed.

## Motivation

Antigravity's 2026-10-20 independent remediation review passed the previous seven data-integrity checks. One explicit follow-up remained: `trade_calc_mode` was captured but not checked against the formula assumed by the backtesting engine. GoldFlow computes price-distance cash risk using contract size, so not every MT5 calculation mode is interchangeable.

The official MQL5 `ENUM_SYMBOL_CALC_MODE` reference documents linear profit formulas of `(close_price - open_price) * Contract_Size * Lots` for FOREX, FOREX_NO_LEVERAGE, CFD, CFDINDEX, CFDLEVERAGE, EXCH_STOCKS, and EXCH_STOCKS_MOEX. Futures modes use tick price/tick size, while bond and collateral modes have different formulas. GoldFlow therefore allows only the linear contract-size group and fails closed for all other or unknown modes. [Official MQL5 reference](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants).

## Implemented changes

- `trade_calc_mode` is now a required audited field and part of the loader's minimum complete-capture field set.
- The audit reports the numeric value, recognized mode name, formula-compatibility status, and allowlist boolean. The name is resolved from symbolic constants exposed by the active MetaTrader5 Python package; there is no hard-coded numeric enum map. The captured name-to-code map is retained in the sidecar and compared to the symbol_info numeric value, failing closed on absent, ambiguous, or inconsistent mappings.
- Missing, malformed, negative, or fractional mode values return `CALC_MODE_UNVERIFIED`. A present numeric mode without a uniquely resolved name, active-package source marker, or non-empty constant map cannot be considered complete; absent `symbol_info()` remains `unavailable` even when the Python module exposes constants.
- Futures/tick-price, bond, collateral, unknown, and other non-allowlisted values return `CALC_MODE_UNSUPPORTED`.
- Tick-value arithmetic runs only when the calculation mode is allowlisted, all three currency assumptions are present and supported (`XAU`/`USD`/`USD`), and contract size, tick size, and tick value are positive finite numbers.
- Strict backtests remain gated on the overall matched-spec status; unsupported or unverified modes block execution.
- Audit output now presents calculation mode and compatibility explicitly. All five embedded metrics JSON snapshots were refreshed from the current `reports/execution_spec_audit.json` object; trade calculations were preserved.

## Verification

- Prior implementation baseline: **322 passed**. After dynamic constant-map resolution and completeness regression tests, the full suite passes **327 tests**.
- `py -3.13 -m compileall -q src pages scripts tests app.py`: passed.
- `py -3.13 scripts/research_readiness.py`: `READY_WITH_WARNINGS`, exit code 0.
- `py -3.13 scripts/audit_execution_specs.py`: `ASSUMPTIONS_ONLY`, exit code 2 (expected because existing sidecars have not had live specifications captured from the intended MT5 terminal).
- The strict M5 backtest gate is expected to refuse with `ASSUMPTIONS_ONLY`; automated tests additionally prove that an unsupported calculation mode blocks before CSV loading.

## Remaining boundary

This allows formulas that match the simulator model; it does not validate that a particular broker's current `XAUUSD` uses one of those modes until `scripts/capture_mt5_execution_specs.py` runs on the intended terminal. It also does not authenticate historical data provenance, reproduce tick-level order sequence, or prove future trading performance.


## Phase 3D.3.2.1 — Dynamic calculation-mode resolution hardening

- Removed the risk of treating undocumented numeric enum IDs as stable constants. `src/data/loader.py` now snapshots `SYMBOL_CALC_MODE_*` values exported by the active MetaTrader5 Python package and resolves the `symbol_info().trade_calc_mode` name only when exactly one constant matches. The captured map is persisted for audit-time code/name comparison.
- `captured_complete` now requires a non-empty map and a resolved symbolic name/source, and an absent `symbol_info()` stays `unavailable` even if the package exports enum constants. The audit emits `CALC_MODE_MISMATCH` when the numeric code disagrees with the captured map.
- Regression coverage includes missing `symbol_info` despite module constants, empty and ambiguous constant maps, and code/name/map mismatch. SMC signals, backtest fills, holding limits, and trade P&L calculations remain unchanged.


## Final dynamic-resolution verification addendum (2026-10-20)

- `python -m pytest tests/ -q`: **327 passed**.
- `python -m compileall -q src pages scripts tests app.py`: passed.
- `python scripts/research_readiness.py`: `READY_WITH_WARNINGS`, exit 0.
- `python scripts/audit_execution_specs.py`: `ASSUMPTIONS_ONLY`, exit 2, expected because the packaged sidecars lack live MT5 instrument captures.
- `python scripts/run_smc_backtest.py --timeframes M5 --require-matched-execution-spec`: backtest refused before execution with `ASSUMPTIONS_ONLY`, exit 2, as intended.
- All five metric JSON snapshots contain the current `reports/execution_spec_audit.json` object; trade/config payloads remain identical to the previous Phase 3D.3.1 package.

## Phase 3D.3.2.2 — Cross-platform path normalization (2026-10-20)

- Standardized serialized `sidecar_path` values using `PurePath.as_posix()` so the audit uses forward-slash paths on Windows and POSIX.
- Added a dedicated test using `PureWindowsPath`, making the Windows path behavior testable on any platform.
- Verification: **328 tests passed**; compilation passed; readiness remains `READY_WITH_WARNINGS`; the audit and strict backtest correctly remain blocked with `ASSUMPTIONS_ONLY` until live MT5 specification capture.
- Report-snapshot status/count consistency passed across all five metrics JSON files. No SMC rules, holding periods, execution assumptions, or trade metrics were changed.
- Antigravity review brief: `docs/ANTIGRAVITY_REVIEW_PHASE3D3_2_2.md`.
