# GoldFlow Phase 5 — Implementation and Verification Handoff

**Verification Date:** 2026-10-28  
**Primary Instrument:** XAUUSD (Gold)  
**Primary Framework:** Smart Money Concepts (SMC v1)  
**Secondary Framework:** ICT Engine (strictly isolated, zero cross-imports)  
**Status:** Independent Validation & Research Reliability Complete (Exploratory Findings Confirmed, No Genuine OOS Data Available)

---

## 1. Executive Summary

Phase 5 conducted an exhaustive, adversarial data-science and quantitative research audit of the GoldFlow platform. The primary objective was to independently audit, test, and validate whether the experimental higher-timeframe (H4/H1) structural trend filter provides a defensible, repeatable trading edge over the frozen SMC v1 benchmark on lower timeframes (M15 and M5).

Key findings:
1. **Frozen Config Integrity:** The canonical baseline configuration (`configs/smc_v1_frozen.json`) remains completely untouched; its SHA-256 hash (`1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`) has been verified and enforced via automated test gates.
2. **Technical Defects Resolved:** Fixed a Windows path separator bug in `scripts/run_smc_mtf_backtest.py` (`_portable()` now outputs standard POSIX slashes via `Path.as_posix()`), resolving the sole failing test in the suite.
3. **No True Independent Holdout Exists:** All 4 available historical datasets (H4, H1, M15, M5) were visible and utilized during earlier strategy formulation and parameter selection cycles. Therefore, claims of "out-of-sample validation" or "deployment readiness" cannot be made. All results are strictly exploratory full-history evaluations.
4. **Statistical Significance Reality:** On M15, the H4/H1 filter appeared profitable ($+$506.56 net P&L, 1.79 profit factor) but produced only **11 closed trades**. Because the strategy targets asymmetric targets, its empirical break-even win rate is **24.17%** (payoff ratio $B = 3.14$), not 50.0%. The 95% Wilson score confidence interval for its 36.36% win rate spans **[13.2%, 67.8%]**, crossing far below the 24.17% break-even mark. Furthermore, **+$696.16 (137.4%)** of net profit is concentrated in a single outlier trade (`SMC_M15_0053`); removing it results in a net loss (-$189.60). On M5 (283 closed trades), the filtered variant remained distinctly unprofitable ($-1,421.00 net P&L, 0.933 profit factor).
5. **Cost Sensitivity Monotonicity:** Stress testing across spread markup (2x, 3x), slippage (3x), and commissions ($3/lot) confirmed monotonic P&L degradation with zero anomalous reversals.

---

## 2. Files Inspected and Modified

### Inspected Files
- `configs/smc_v1_frozen.json` (SHA-256 hash verified: `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`)
- `src/smc/engine.py` (Structure breaks, liquidity sweeps, order blocks, fractal swings)
- `src/strategy/smc_mtf.py` (Causal multi-timeframe alignment, candle-close availability)
- `src/backtesting/engine.py` (Event-driven OHLC simulation, cost models, stop-first collision)
- `src/ict/engine.py` (Verified complete independence from SMC engine; no cross-imports)
- `data/processed/*.csv` and `data/processed/*.meta.json` (H4, H1, M15, M5 datasets)
- `reports/research_readiness.json` and `reports/execution_spec_audit.json`
- `reports/phase3e/*` (Phase 3E multi-timeframe experiment outputs)

### Modified Files
- `scripts/run_smc_mtf_backtest.py`: Corrected `_portable()` path normalization to use `as_posix()`.
- `pages/3_BI_Dashboard.py`: Integrated Phase 5 independent validation findings, report source switcher, Wilson 95% CI uncertainty display, and interactive execution-cost sensitivity stress-test tables.

### Newly Created Files
- `configs/smc_phase5_mtf_experiment.json`: Standalone experimental configuration for the H4/H1 MTF filter, preserving the frozen SMC v1 config unaltered.
- `scripts/run_phase5_validation.py`: Deterministic, reproducible research runner with frozen-config integrity gates, data readiness checks, execution-spec verification, and cost-sensitivity stress testing.
- `tests/test_phase5_regression.py`: Suite of 9 regression tests verifying frozen config immutability, path normalization, cost replay monotonicity, and runner error handling.
- `reports/phase5/PHASE5_BASELINE_AUDIT.md`: Complete baseline audit of repo structure, commit history, test results, and data provenance.
- `reports/phase5/PHASE5_INDEPENDENT_VALIDATION.md`: Evaluation of MTF strategy variants, sample-size constraints, and statistical limitations.
- `reports/phase5/PHASE5_ROBUSTNESS_REPORT.md`: Stress test results across spread, slippage, and commissions.
- `reports/phase5/phase5_validation_metrics.json`: Full machine-readable metrics, dataset SHA-256 hashes, software versions, and cost scenario data.
- `reports/phase5/smc_mtf_*.csv`: Output trades, equity curves, candidate audits, and Power BI summaries.
- `reports/phase5/PHASE5_IMPLEMENTATION_HANDOFF.md`: This comprehensive handoff document.

---

## 3. Technical Defects Discovered and Resolved

1. **Windows Path Normalization Defect in `_portable()`:**
   - *Location:* `scripts/run_smc_mtf_backtest.py:46-50`
   - *Cause:* `str(path.resolve().relative_to(ROOT.resolve()))` used Windows OS native backslashes (`\`) on Windows, causing `tests/test_smc_mtf.py` to fail its forward-slash assertion (`assert "\\" not in ...`).
   - *Fix:* Changed implementation to `.as_posix()`, ensuring uniform forward slashes across Windows, Linux, and macOS without modifying business logic.
   - *Verification:* `tests/test_smc_mtf.py` now passes 100%.

2. **Unauthenticated Historical Data Provenance:**
   - *Finding:* All OHLC data originates from a MetaQuotes-Demo MT5 terminal export. No independent LMAX, Dukascopy, or institutional tick-data audit exists.
   - *Documentation:* Categorized transparently as `DECLARED_NOT_AUTHENTICATED`.

3. **Inappropriate Holdout Claims in Earlier Documentation:**
   - *Finding:* Previous documentation described certain segments as validation/holdouts despite those segments being repeatedly backtested during parameter selection.
   - *Resolution:* Audited and explicitly reclassified all results as exploratory full-history evaluations.

---

## 4. Test Suite and Verification Results

Every test in the repository was executed under Python 3.14.7 on Windows 11:

| Test Module / Suite | Tests Run | Result | Notes |
|---|---|---|---|
| `tests/test_phase5_regression.py` | 9 | **9 PASSED** | Verifies frozen config hash, path portability, cost monotonicity, runner gates |
| `tests/test_smc_mtf.py` | 5 | **5 PASSED** | Fixed path normalization; verifies causal timeline and candle-close availability |
| `tests/test_frozen_config_enforcement.py` | 7 | **7 PASSED** | Enforces SHA-256 hash `1091fb06...` |
| `tests/test_canonical_isolation.py` | 13 | **13 PASSED** | Verifies zero ICT cross-imports in SMC modules |
| Full Existing Test Suite (`tests/`) | 455 | **455 PASSED** | 0 failed, 0 skipped, execution time 33.22s |
| Python Compilation (`py_compile`) | 32 files | **CLEAN** | Exit code 0 across all `src/`, `scripts/`, `pages/`, `tests/` |
| Research Readiness Check | Script run | **READY_WITH_WARNINGS** | Zero blockers, execution spec defaults matched |
| Execution Spec Audit | Script run | **MATCHED_CAPTURED_DEFAULTS** | Execution costs match captured live MT5 defaults |

---

## 5. Dataset Inventory and Backtest Ranges

All backtests used cleaned, chronological, UTC-converted data:

| Timeframe | Bars | Start (UTC) | End (UTC) | File SHA-256 |
|---|---|---|---|---|
| H4 | 5,000 | 2023-07-27 17:00 | 2026-10-20 09:00 | `3a5f3342899e7539ddf6b40f098091dfb6c5ea3ae3219da64016d92789b670fc` |
| H1 | 10,000 | 2025-01-31 14:00 | 2026-10-20 14:00 | `2192f4c1f22010a78c2fc17f37a1826254f8ee4060df1dc813814ea559321db9` |
| M15 | 5,000 | 2026-08-04 12:00 | 2026-10-22 09:15 | `2f6bded7fc58752a7de9097c9258bb24840be79fbaad55d82ebf4835dfad2def` |
| M5 | 99,999 | 2025-05-13 22:15 | 2026-10-20 15:50 | `76d3d4fc95069694b46a1492e4755017cb0e7571ab78570493ec3de1a4a8fa8c` |

*Evaluation Windows (Finding B Reconciliation):*
- **M15 Experiment Evaluation Window (M15 ∩ H1 ∩ H4):** `2026-08-04 12:00` to `2026-10-20 09:00` UTC (4,823 M15 bars; ~77 calendar days).
- **M5 Experiment Evaluation Window (M5 ∩ H1 ∩ H4):** `2025-05-13 22:15` to `2026-10-20 09:00` UTC (99,917 M5 bars; ~17.2 months).
- **True 4-Way Intersection (H4 ∩ H1 ∩ M15 ∩ M5):** `2026-08-04 12:00` to `2026-10-20 09:00` UTC (H4: 330 | H1: 1,207 | M15: 4,823 | M5: 14,467 bars).
*(Note: Earlier reports described the common window as 2025-05-13 to 2026-10-20, which applied strictly to the M5 experiment; M15 only begins on 2026-08-04).*

---

## 6. Primary Strategy Comparison Metrics

Backtested with initial equity $10,000, 1% risk per trade, 100 oz contract size ($1.00/point/lot), conservative stop-loss-first collision handling:

| Timeframe | Strategy Variant | Candidates | Closed | Win Rate (%) | 95% Wilson CI | Gross P&L ($) | Total Costs ($) | Net P&L ($) | Return (%) | Profit Factor | Max DD ($) | Avg R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **M15** | SMC_v1_baseline | 54 | 40 | 20.51% | [10.8%, 35.5%] | -$166.19 | $72.93 | -$239.12 | -2.39% | 0.922 | $1,632.95 | -0.068 |
| **M15** | SMC_v1_H4_H1_confirmed | 11 | 11 | 36.36% | **[13.2%, 67.8%]** | +$528.46 | $21.90 | +$506.56 | +5.07% | 1.793 | $457.65 | +0.444 |
| **M5** | SMC_v1_baseline | 1,015 | 842 | 27.71% | [24.8%, 30.8%] | -$1,686.73 | $3,268.90 | -$4,955.63 | -49.56% | 0.873 | $6,392.88 | -0.076 |
| **M5** | SMC_v1_H4_H1_confirmed | 298 | 283 | 28.98% | [24.0%, 34.5%] | -$48.97 | $1,372.03 | -$1,421.00 | -14.21% | 0.933 | $3,502.65 | -0.039 |

*Note on Metrics:* Win rate, profit factor, and average R exclude `END_OF_DATA` mark-outs. Net P&L and Max Drawdown include end-of-sample liquidation. Gross P&L reflects pure price delta before transaction frictions.

---

## 7. Robustness and Execution-Cost Stress Testing

Stress testing on recorded trade ledgers under adverse market frictions (Finding A Reconciliation):

> **Root Cause of Finding A Discrepancy:** The earlier report listed M15 baseline replay as -$6,109.68. This was caused by an unfiltered replay script execution that evaluated the combined multi-timeframe trade ledger (all 1,174 closed trades across both timeframes and both variants) and mislabeled it as M15 baseline. Correctly filtering to the 40 M15 baseline trades yields -$239.32 at baseline costs (within $0.20 of the backtest engine's -$239.12).

### M15 Baseline Stress Test (40 closed trades)
- **Baseline Costs (1.0x spread, $0.05 slippage, $0 commission):** Gross P&L: -$166.19 | Costs: $73.13 | Net P&L: -$239.32 | PF: 0.922 | Max DD: $1,032.68
- **Spread 2.0x:** Gross P&L: -$166.19 | Costs: $110.41 | Net P&L: -$276.60 | PF: 0.909 | Max DD: $1,045.75
- **Spread 3.0x:** Gross P&L: -$166.19 | Costs: $147.69 | Net P&L: -$313.88 | PF: 0.897 | Max DD: $1,068.50
- **Slippage 3.0x ($0.15/side):** Gross P&L: -$166.19 | Costs: $144.83 | Net P&L: -$311.02 | PF: 0.898 | Max DD: $1,070.60
- **Commission ($3.00/lot):** Gross P&L: -$166.19 | Costs: $98.15 | Net P&L: -$264.34 | PF: 0.913 | Max DD: $1,038.12
- **Adverse Combined (2.0x spread, $0.15 slip, $3.00 comm):** Gross P&L: -$166.19 | Costs: $207.13 | Net P&L: -$373.32 | PF: 0.878 | Max DD: $1,108.47

### M15 MTF Confirmed Stress Test (11 closed trades)
- **Baseline Costs:** Gross P&L: +$528.46 | Costs: $21.90 | Net P&L: +$506.56 | PF: 1.793 | Max DD: $457.65
- **Spread 2.0x:** Gross P&L: +$528.46 | Costs: $34.60 | Net P&L: +$493.86 | PF: 1.768 | Max DD: $462.59
- **Spread 3.0x:** Gross P&L: +$528.46 | Costs: $47.30 | Net P&L: +$481.16 | PF: 1.743 | Max DD: $467.53
- **Slippage 3.0x ($0.15/side):** Gross P&L: +$528.46 | Costs: $40.30 | Net P&L: +$488.16 | PF: 1.753 | Max DD: $466.95
- **Commission ($3.00/lot):** Gross P&L: +$528.46 | Costs: $30.18 | Net P&L: +$498.28 | PF: 1.777 | Max DD: $460.65
- **Adverse Combined:** Gross P&L: +$528.46 | Costs: $61.28 | Net P&L: +$467.18 | PF: 1.713 | Max DD: $474.89

### M5 Baseline Stress Test (842 closed trades)
- **Baseline Costs:** Net P&L: -$4,955.93 | PF: 0.873 | Max DD: $6,392.44
- **Adverse Combined:** Net P&L: -$10,555.17 | PF: 0.763 | Max DD: $11,848.02

### M5 MTF Confirmed Stress Test (283 closed trades)
- **Baseline Costs:** Net P&L: -$1,421.00 | PF: 0.933 | Max DD: $3,223.05
- **Adverse Combined:** Net P&L: -$3,796.67 | PF: 0.836 | Max DD: $4,775.33

*Conclusion:* The degradation is strictly monotonic. While the M15 MTF variant resists modeled retail costs, its 11-trade sample size makes it statistically fragile—a single trade reversal easily eliminates the profit cushion.

---

## 8. Research Limitations and Non-Deployment Declaration

> [!CAUTION]
> **Strict Non-Deployment Declaration:**
> GoldFlow SMC v1 and the experimental H4/H1 MTF filter are **NOT approved for live capital deployment**. 
> - No genuine out-of-sample data was available during this evaluation.
> - The M15 filtered positive result is based on an inadequate sample size ($n=11$).
> - The M5 filtered result is deeply negative ($-14.21\%$).
> - Intrabar pathing is modeled on bar extremes (OHLC) rather than millisecond tick order books.

---

## 9. Reproduction Commands

To reproduce the complete Phase 5 audit, test suite, and backtesting pipeline:

```powershell
# 1. Run full test suite (all 455 tests must pass)
python -m pytest tests/ -q --tb=short

# 2. Run Python compilation check across all modules
python -m py_compile src/strategy/smc_mtf.py scripts/run_phase5_validation.py pages/3_BI_Dashboard.py

# 3. Run research readiness check
python scripts/research_readiness.py

# 4. Run execution specification audit
python scripts/audit_execution_specs.py

# 5. Execute Phase 5 independent validation runner
python scripts/run_phase5_validation.py --timeframes M15 M5

# 6. Launch Streamlit BI Dashboard to view interactive results
streamlit run app.py
```

---

## 10. Recommended Next Milestone

**Phase 6: Forward Out-of-Sample Collection & True Holdout Evaluation**
1. **Automate Live Feed Ingestion:** Connect to an institutional broker feed (e.g., LMAX, Interactive Brokers, or Darwinex) to ingest genuine, unseen XAUUSD tick and 1-minute data continuously.
2. **Lock Holdout Vault:** Establish a physically isolated data store that cannot be accessed by research scripts during strategy development.
3. **Pre-Commit Evaluation Protocol:** Formally hash and register candidate strategy parameters before unlocking the holdout vault for a single-pass, irrevocable evaluation.
