# Antigravity Follow-up Review — Phase 3D.3.1 Remediation

## Goal
Independently review the applied fixes for Antigravity's 2026-10-20 audit. Do not modify or optimize SMC signal rules, holding periods, or report P&L. Focus on data integrity and diagnostics.

## Changed files
- `scripts/capture_mt5_execution_specs.py`
- `src/research/execution_spec_audit.py`
- `scripts/audit_execution_specs.py`
- `tests/test_capture_mt5_execution_specs.py`
- `tests/test_execution_spec_audit.py`
- `docs/PHASE3D3_EXECUTION_VALIDATION.md`
- `reports/SMC_PHASE_HANDOFF.md`

## Required independent checks
1. Review the staged backup lifecycle and exception path. Simulate a failure before the second sidecar write and a writer that replaces a target and then raises. Confirm all attempted files are restored byte-for-byte when rollback is available; confirm a rollback failure is not hidden and its original backup is retained for manual recovery.
2. Check for orphaned `.rollback.*.tmp` files after success, staging failure, write failure and rollback failure.
3. Verify no OHLC CSVs are read or changed by capture, and no account login/balance/equity data is persisted.
4. Confirm `wrong_type_fields` catches booleans, NaN, ±infinity and malformed numeric strings, while absent/null fields stay distinguishable and strict gate behavior is unchanged.
5. Confirm `digits=0`, negative digits, and fractional digits fail validation.
6. Confirm `trade_calc_mode` allows only documented linear contract-size profit modes and blocks tick-price/futures, bond, collateral, unknown, and malformed modes.
7. Verify current metrics JSON audit snapshots match `reports/execution_spec_audit.json` and that only audit metadata, not trade calculations, changed.

## Reproduction commands
```powershell
py -3.13 -m pytest tests/ -q
py -3.13 -m compileall -q src pages scripts tests app.py
py -3.13 scripts/research_readiness.py
py -3.13 scripts/audit_execution_specs.py
```

Expected: test suite passes; compile succeeds; readiness remains `READY_WITH_WARNINGS`; data audit remains `ASSUMPTIONS_ONLY` (exit 2) until a real matching MT5 capture is performed. Return findings with severity, exact file/line, reproducer, and proposed test. Do not claim trading profitability or ultimate win rate from this engineering audit.
