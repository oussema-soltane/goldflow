# GoldFlow Phase 5 — Baseline Audit

**Audited:** 2026-10-26T12:42:57Z
**Auditor:** Phase 5 Stage A automated inspection
**Repository root:** `GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated`
**Git history:** single commit (`ad9807f`) — working-tree modifications are untracked

---

## 1. Repository Structure — Verified

All claimed directories and files are physically present.

- `configs/smc_v1_frozen.json` — frozen strategy configuration
- `data/processed/` — 4 timeframes (H4, H1, M15, M5) with `.meta.json` sidecars
- `pages/` — 4 Streamlit pages
- `reports/phase3e/` — Phase 3E MTF experiment artifacts
- `scripts/` — 16 research/diagnostic scripts
- `src/` — backtesting, smc, ict, strategy, research, data, visualization
- `tests/` — 27 test files

---

## 2. Frozen Strategy Configuration

**File:** `configs/smc_v1_frozen.json`
**SHA-256 (live computed):**  `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`
**SHA-256 (Phase 3E record):** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`

**RESULT: HASH MATCHES — configuration is intact and unmodified.**

Key parameters (verified from file):

| Parameter | Value |
|---|---|
| Swing window k | 2 bars |
| Confirmation delay | 2 bars |
| Equal-level tolerance | 0.50 price units |
| Max sweep-to-CHoCH | 20 bars |
| Max CHoCH-to-retest | 20 bars |
| Stop buffer | 0.50 price units |
| Fixed RR fallback | 2.0 |
| Minimum RR | 1.0 |
| Risk fraction | 1% equity |
| Initial capital | $10,000 USD |
| Contract size | 100 oz |
| Point size | 0.01 |
| Spread fallback | $0.20 USD |
| Slippage per side | $0.05 USD |
| Commission per lot per side | $0.00 |
| Conservative stop-first collision | true |
| ICT-specific rules | NONE |

---

## 3. Dataset Inventory — Verified

| Timeframe | Rows | Start (UTC) | End (UTC) | Source | Provenance |
|---|---|---|---|---|---|
| H4 | 5,000 | 2023-07-27 17:00 | 2026-10-20 09:00 | MT5 API | declared_not_independently_verified |
| H1 | 10,000 | 2025-01-31 14:00 | 2026-10-20 14:00 | MT5 API | declared_not_independently_verified |
| M15 | 5,000 | 2026-08-04 12:00 | 2026-10-22 09:15 | MT5 API | declared_not_independently_verified |
| M5 | 99,999 | 2025-05-13 22:15 | 2026-10-20 15:50 | MT5 API | declared_not_independently_verified |

Coverage notes:
- M15 ends approximately 2 days later than H4/H1/M5.
- Effective common window (all 4 TFs): approximately 2025-05-13 to 2026-10-20 (~17 months).
- Broker: MetaQuotes-Demo. No independent third-party provenance.
- Timestamp correction applied: −10,800 s (Europe/Athens UTC+3 to UTC). Status: `verified`.
- Known discrepancy: `symbol_info.trade_tick_value` reports 0.1 but `order_calc_profit`
  confirms 1.0 USD/tick/lot. Engine uses the verified contract formula (100 oz × 0.01).

---

## 4. Research Readiness (Live Run 2026-10-26)

**Command:** `python scripts/research_readiness.py`
**Result:** `READY_WITH_WARNINGS`
Blockers: none  
Warnings: none reported

---

## 5. Execution-Specification Audit (Live Run 2026-10-26)

**Command:** `python scripts/audit_execution_specs.py`
**Result:** `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE`

| Symbol | Timeframe | Status |
|---|---|---|
| XAUUSD | H1 | MATCHED_CAPTURED_DEFAULTS |
| XAUUSD | H4 | MATCHED_CAPTURED_DEFAULTS |
| XAUUSD | M15 | MATCHED_CAPTURED_DEFAULTS |
| XAUUSD | M5 | MATCHED_CAPTURED_DEFAULTS |

The `UNVERIFIED_PROVENANCE` suffix in the overall status correctly reflects that
the captured specs originate from the same MT5 terminal as the data.

---

## 6. Compilation Check

**Command:** `python -m compileall src/ scripts/ pages/`
**Result:** Exit code 0, no errors.

---

## 7. Test Suite Results — Actual Execution

**Command:** `python -m pytest tests/ --tb=short -q`
**Duration:** 47.47 seconds
**Result:** **1 FAILED, 445 PASSED (446 total)**

### The Failing Test

`tests/test_smc_mtf.py::test_execution_audit_paths_are_project_relative_when_possible`

**Root cause:** `_portable_execution_audit_paths()` in `scripts/run_smc_mtf_backtest.py`
calls `Path.relative_to()`. On Windows, `Path` uses backslash separators, producing
`data\\processed` where the test expects `data/processed`.

**Assessment:** Windows path separator normalization bug only. Does not affect any
backtest computation, signal detection, trade ledger, or equity curve.
**Fix:** Use `Path.as_posix()` to normalize. Applied in Stage B.

### Count Reconciliation

| Source | Count |
|---|---|
| Phase 3D.3.2 release note | 327 passed |
| Phase 5 package claim | 446 passing |
| Actual current state | **445 passed, 1 failed** |

The release note describes Phase 3D.3.2. Subsequent development added tests.
The 1 failing test is the path-separator issue above. No tests were deleted or weakened.

---

## 8. Phase 3E Results (Stored Artifacts — Not a Live Re-Run)

Values read from `reports/phase3e/smc_mtf_metrics.json`.
JSON payload and Markdown report are numerically consistent.

| Timeframe | Variant | Candidates | Closed | Win Rate | Net P&L | Return | PF | Max DD | Avg R |
|---|---|---|---|---|---|---|---|---|---|
| M15 | SMC_v1_baseline | 54 | 40 | 20.51% | −$239.12 | −2.39% | 0.92 | $1,632.95 | −0.07 |
| M15 | SMC_v1_H4_H1_confirmed | 11 | 11 | 36.36% | +$506.56 | +5.07% | 1.79 | $457.65 | +0.44 |
| M5 | SMC_v1_baseline | 1,015 | 842 | 27.71% | −$4,955.63 | −49.56% | 0.87 | $6,392.88 | −0.08 |
| M5 | SMC_v1_H4_H1_confirmed | 298 | 283 | 28.98% | −$1,421.00 | −14.21% | 0.93 | $3,502.65 | −0.04 |

Win rate, PF, and Avg R exclude END_OF_DATA exits.
Net P&L and Max DD include end-of-data liquidation.

> **Critical limitation (stated in the artifact):** "The bundled records have already
> been examined during earlier phases; this is not an untouched out-of-sample result."

---

## 9. ICT Engine Independence — Verified

`src/ict/` has no imports from `src/smc/` or `src/strategy/`.
The SMC engine does not import from `src/ict/`.
The frozen config `scope_warnings` explicitly states: "No ICT-specific rules included."

---

## 10. Dependency Versions (Live Environment)

| Package | Required | Installed |
|---|---|---|
| Python | — | 3.14.7 |
| pandas | >=2.2.0 | 3.0.6 |
| numpy | >=1.26.0 | 2.5.3 |
| plotly | >=5.24.0 | 7.1.0 |
| scikit-learn | >=1.5.0 | 1.9.1 |
| pytest | >=8.0.0 | present (47s run) |
| psutil | >=5.9.0 | present |
| tzdata | >=2024.1 | present |
| streamlit | >=1.40.0 | 1.64.0 |
| MetaTrader5 | >=5.0.5735 | 5.0.6231 |

---

## 11. Known Limitations and Required Actions

| # | Issue | Severity | Action |
|---|---|---|---|
| 1 | Windows path separator bug in `_portable_execution_audit_paths` | Low | Fix with `as_posix()` — Stage B |
| 2 | No independently authenticated data provenance | Structural | Declare in all reports |
| 3 | All data examined in prior phases — no untouched holdout | Critical | No genuine OOS possible — Stage C |
| 4 | M15 ends 2 days later than other TFs | Minor | Document only |
| 5 | Common window ~17 months (M5 start = 2025-05-13) | Informational | Limits split power |
| 6 | MT5 import requires live Windows terminal | Informational | New capture needs terminal |

---

## 12. Summary

| Area | Status |
|---|---|
| Repository structure | VERIFIED — all files present |
| Frozen config integrity | VERIFIED — SHA-256 matches |
| ICT engine independence | VERIFIED — no cross-imports |
| Data readiness | READY_WITH_WARNINGS — no blockers |
| Execution spec audit | MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE |
| Compilation | CLEAN — exit code 0 |
| Test suite | 1 FAILING (path separator) / 445 passing |
| Phase 3E artifacts | STORED VALUES VERIFIED — not re-run live |
| Independent holdout | UNAVAILABLE — all data examined in prior phases |
| Data provenance | UNVERIFIED — MetaQuotes-Demo only |

**Overall conclusion:** The repository is structurally intact and claims are
consistent with what is verifiable. One test fails due to a Windows path
normalization bug with no impact on research correctness. No genuine independent
evaluation period exists in the current datasets. All Phase 3E metrics are
exploratory full-history results on data visible during strategy development.
Phase 5 work must clearly label all results as exploratory and implement an
evaluation framework ready to receive genuinely new data.
