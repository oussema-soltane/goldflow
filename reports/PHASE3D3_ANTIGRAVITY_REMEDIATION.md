# GoldFlow Phase 3D.3.1 — Independent Audit Remediation

**Date (UTC):** 2026-10-20  
**Scope:** broker execution-spec capture, execution-spec audit diagnostics, tests and report snapshots only. No SMC signal or holding-period parameters changed.

## Findings addressed

| Finding | Severity | Remediation | Verification |
|---|---|---|---|
| Cross-sidecar partial update after OS write failure | Medium | Exact original bytes are staged to same-filesystem backup files before any sidecar write. Attempted sidecars are restored via `os.replace` if a later write fails. Incomplete rollback now raises an explicit `RuntimeError` with affected paths and preserves the failed file's original backup for manual recovery. | Tests simulate failure before the second write, an error after the second atomic replacement, and failure during rollback. |
| Present-but-invalid numeric value reported only as missing | Low | Audit result includes `wrong_type_fields` for unusable present values, while retaining the historic `missing_required_fields` behavior for strict-gate compatibility. Markdown audit includes this column. | Tests cover boolean, NaN, infinity and malformed numeric strings. |
| Invalid `digits` boundary | Low | Numeric precision must be an integer of at least 1. | Regression tests verify zero, negative and fractional digits yield `MISSING_SPECIFICATIONS`. |
| Missing coverage for malformed values and missing account metadata | Low | Added tests for missing account currency and no broker-server identity; the capture fixture now contains `trade_tick_value`. At the time of this initial remediation, `trade_calc_mode` was captured but not yet allowlisted; that gap was addressed in Phase 3D.3.2 below. | Targeted tests and full suite pass. |

## Verification run

- `python -m pytest tests/ -q` — **304 passed**.
- `python -m compileall -q src pages scripts tests app.py` — **passed**.
- `python scripts/research_readiness.py` — `READY_WITH_WARNINGS`, exit 0.
- `python scripts/audit_execution_specs.py` — `ASSUMPTIONS_ONLY`, exit 2 as expected: the packaged sidecars do not contain a real live-terminal MT5 symbol specification.
- Strict backtest gating remains correct: it should not proceed until the actual instrument specification is captured and reconciled against the active configuration.

The audit snapshot embedded in the full-history, common-window, lifecycle, and holdout metrics JSON files was refreshed from the same current audit output. This refresh updates audit metadata only; it does not re-run or modify reported trade calculations.

## Remaining limitations

1. The script has not been connected to the user's logged-in MT5 terminal in this environment. Actual contract, point, tick and lot specifications remain unknown here.
2. Rollback is explicit and robust for ordinary write/replace failures, but no multi-file filesystem operation is universally atomic if rollback itself also fails. The implementation raises a high-visibility error in that case.
3. `trade_calc_mode` was the remaining gap and is now allowlisted only for documented linear contract-size profit modes. The actual broker mode still must be captured from the intended MT5 terminal; tick-price/futures, bond, collateral, unknown, and malformed modes block strict validation.
4. Historical data provenance and tick-level execution remain independently unverified. A matching specification audit is not evidence of a trading edge or a high win rate.


## Follow-up engineering update (2026-10-20)

The calculation-mode limitation described above was addressed in Phase 3D.3.2. The live mode is now required and must belong to a documented linear contract-size profit formula allowlist before tick-value arithmetic or strict validation can pass. Futures/tick-price, bond, collateral, unknown and malformed modes are blocked. The actual mode on the operator's MT5 terminal remains unobserved in this offline build environment.


## Follow-up: calculation-mode source and capture completeness (2026-10-20)

The independent follow-up recommended explicit validation of `trade_calc_mode`. The subsequent implementation initially considered numeric enum IDs, then was hardened to avoid hard-coded IDs altogether: the capture path resolves symbolic mode names from the active MetaTrader5 package and stores its observed name/code map. The audit checks that the numeric mode matches that map, allowlists only documented contract-size formula names, and reports a distinct `CALC_MODE_MISMATCH` when the code/name/map disagree. A regression test also ensures a missing `symbol_info()` is `unavailable` even when module constants exist. No signal or trade execution logic changed.


Final Phase 3D.3.2.1 verification: **327 tests passed**; compilation passed; readiness is `READY_WITH_WARNINGS`; execution-spec audit is `ASSUMPTIONS_ONLY` (expected until the intended terminal's live symbol specification is captured). Strict backtest preflight refused to run with exit code 2. Embedded audit snapshots are current and trade/config calculations remain invariant to the Phase 3D.3.1 package.
