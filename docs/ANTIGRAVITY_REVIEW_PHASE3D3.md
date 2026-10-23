# Antigravity Independent Review — GoldFlow Phase 3D.3

## Mission

Perform an independent correctness review of the broker execution-specification guardrails and the updated Phase 3D reports. The goal is simulator correctness and trustworthy risk/accounting—not optimizing the SMC entry rules or selecting whichever historical scenario has the best P&L.

## Current known state

- Latest local verification: 293 tests passed; `compileall` passed.
- Readiness reports `READY_WITH_WARNINGS` with no critical blockers.
- `scripts/audit_execution_specs.py` reports `ASSUMPTIONS_ONLY`, expected because the bundled metadata sidecars do not contain a real captured MT5 instrument specification. Strict mode should therefore block.
- Historical source provenance remains `declared_not_independently_verified`.
- The MT5 capture utility has not been run against the user's logged-in terminal from this environment.

## Files to inspect

- `src/research/execution_spec_audit.py`
- `src/data/loader.py`
- `scripts/capture_mt5_execution_specs.py`
- `scripts/audit_execution_specs.py`
- `scripts/run_smc_backtest.py`
- `scripts/run_smc_lifecycle_stress.py`
- `scripts/run_smc_validation.py`
- `pages/2_Backtesting.py`
- `tests/test_execution_spec_audit.py`
- `tests/test_capture_mt5_execution_specs.py`
- `docs/PHASE3D3_EXECUTION_VALIDATION.md`

## Required audit questions

1. Does capture read the intended terminal's actual symbol and account fields, and reject symbol/server identity mismatches before any sidecar is written?
2. Is capture atomic/all-or-nothing across multiple matching sidecars, and can it ever alter processed OHLC CSV files or leak account-login credentials?
3. Are `point`, digits, contract size, lot minimum/step/maximum, tick size/value and account/profit currencies validated without inferring missing data from price decimals?
4. Is the XAU/USD/USD tick-value arithmetic valid under the supported assumptions, and are unsupported calculation modes/currency cases clearly blocked or labeled?
5. Do strict mode and exploratory mode behave as documented in full-history, common-window, holdout, lifecycle CLI and Streamlit paths?
6. Are config mismatch and tick arithmetic findings prioritized coherently, while preserving all detailed diagnostics?
7. Are the newly embedded audit snapshots current and consistent across report JSONs/Markdown?
8. Are there test gaps around malformed MT5 values (`None`, NaN, infinity, booleans), multiple sidecars, missing account currency, server mismatch and a partial-write failure?

## Reproduction commands

```powershell
py -3.13 -m pytest tests/ -q
py -3.13 -m compileall src pages scripts tests app.py -q
py -3.13 scripts/research_readiness.py
py -3.13 scripts/audit_execution_specs.py
py -3.13 scripts/run_smc_backtest.py --timeframes M5
py -3.13 scripts/run_smc_backtest.py --timeframes M5 --require-matched-execution-spec
```

The last strict command is expected to exit nonzero while audit status is `ASSUMPTIONS_ONLY`. Do not report that expected guardrail refusal as a defect.

## Expected deliverable

Return findings sorted by severity with file/line references, a minimal reproducible counterexample for each defect, and recommended tests. Do not modify the SMC signal or holding-period parameters, and do not claim that a high win rate or profitability has been demonstrated. If making fixes, keep them minimal and rerun the full suite and compilation.
