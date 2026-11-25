# GOLDFLOW — FORENSIC AUDIT FINDINGS

**Date:** 2026-11-11  
**Repository HEAD:** `d75ca98995f65506273ca0808c0e5a6d10c80f96`  
**Branch:** `main`  
**Execution Environment:** Windows 11, Python 3.14.7, pytest 9.1.1  
**Audit Status:** COMPLETE — 905 files cataloged in `reports/FORENSIC_FILE_REVIEW_LEDGER.csv`

---

## 1. Executive Summary & Repository Scope

An exhaustive, repository-wide forensic audit was performed across all directories of `GoldFlow_SMC_Primary_Updated`.
No file was marked `FULLY_READ` or `EXECUTION_VERIFIED` merely on account of AST compilation or existence.
Total files reviewed: **905 non-git files**:
- **Execution Verified:** 76 files (all active unit/regression test modules, data loaders, backtest engines, CLI scripts)
- **Fully Read & Inspected:** 111 files (all source code in `src/`, `pages/`, `app.py`, active configs)
- **Structurally Parsed:** 640 files (registered evaluations, quality indexes, metric reports, JSON sidecars)
- **Historical Evidence Preserved:** 77 files (Phase 5/6 historical reports, archives, prior logs)
- **Binary Classified:** 1 file (icon/binary asset)

The test suite was executed in full without skipping or silencing tests: **664 passed in 31.21s** (100% pass rate).

---

## 2. Core Architecture: SMC vs. ICT Framework Independence

### Architectural Separation
- **Primary Research Framework:** Smart Money Concepts (SMC) implemented in `src/smc/` and `src/strategy/smc_setups.py`.
- **Secondary Framework:** Inner Circle Trader (ICT) implemented in `src/ict/`.
- **Cross-Import Check:** Zero cross-imports exist between `src/smc/` and `src/ict/`. The engines are completely decoupled and share only standard data structures (pandas DataFrames, OHLC conventions) and charting infrastructure.

### SMC Engine Implementation & Event Causality
Exhaustive line-by-line inspection of `src/smc/engine.py` (762 lines) and `src/strategy/smc_setups.py` (418 lines) verified:
1. **Fractal Pivots (`detect_smc_swings`):**
   - Lookback `window = 2` bars on each side with strict inequality (`highs[i] > highs[i±j]`).
   - Confirmation is explicitly recorded: `confirmed_index = i + window`.
2. **Event Causality & Non-Anticipation (`detect_smc_structure_breaks`):**
   - Swings are only made available for BOS/CHoCH detection when `confirmed_index < i` (strict inequality). A swing confirmed on bar `i` cannot trigger a break on bar `i`.
   - Breaks are confirmed strictly on the candle **close** breaching the pivot price.
3. **Liquidity Pools & Sweeps (`detect_smc_liquidity_pools`, `detect_smc_liquidity_sweeps`):**
   - Pools form only after both member pivots are confirmed: `created_index = max(swing1.confirmed_index, swing2.confirmed_index)`.
   - Sweep detection begins strictly at `created_index + 1`. Only the first sweep per pool is recorded.
4. **Order Block Lifecycle (`detect_smc_order_blocks`):**
   - Created at `break_index` (the structure break confirmation bar).
   - Invalidation takes strict precedence over mitigation on ambiguous bars (`close < zone_low` vs touch).
5. **Setup Funnel (`detect_smc_setups_with_funnel`):**
   - Requires preceding sweep within `max_sweep_to_choch_bars` (default 20).
   - Rejection requires price to touch the OB zone AND **close** outside it in the setup direction (`close > block.high` for long).
   - Signal timing is set to the **close of the rejection bar**.
   - **Verdict on Look-Ahead Bias:** Zero look-ahead bias detected in the SMC engine.

---

## 3. Backtesting Engine & Cost Accounting

Line-by-line audit of `src/backtesting/engine.py` (1,053 lines):
1. **Execution Modeling:**
   - Conservative next-bar-open fills: Long enters at `ask_open + slippage`, Short enters at `bid_open - slippage`.
   - Ambiguous bar collision: Conservative stop-first policy is strictly enforced.
   - Spread accounted for: Paid on entry for longs, on exit for shorts.
   - Mark-to-market close-to-close equity curve models floating unrealized P&L and round-turn liquidation costs.
2. **Historical Baseline Reproduction:**
   - Script `scripts/run_smc_backtest.py` was executed directly against canonical data.
   - Exact numerical match obtained across all 4 timeframes:
     * **H4:** 13 closed trades, Net +$448.73, Return +4.49%, Max DD $751.76, PF 1.540
     * **H1:** 61 closed trades, Net -$339.41, Return -3.39%, Max DD $1,265.62, PF 0.917
     * **M15:** 40 closed trades, Net -$239.12, Return -2.39%, Max DD $1,632.95, PF 0.922
     * **M5:** 842 closed trades, Net -$4,955.63, Return -49.56%, Max DD $6,392.88, PF 0.873
3. **Commission Reconciliation:**
   - Replay ledger with $0.07/lot/side vs $0.00:
     * H4: Net +$448.74 (zero) vs +$448.52 ($0.07) | Commission = $0.21 | Delta = -$0.21
     * H1: Net -$339.41 (zero) vs -$340.10 ($0.07) | Commission = $0.70 | Delta = -$0.70
     * M15: Net -$239.12 (zero) vs -$239.70 ($0.07) | Commission = $0.58 | Delta = -$0.58
     * M5: Net -$4,955.63 (zero) vs -$4,977.37 ($0.07) | Commission = $21.75 | Delta = -$21.75

---

## 4. Key Vulnerabilities Identified & Remediated

| ID | Component | Vulnerability | Severity | Remediation Status |
|---|---|---|---|---|
| SEC-01 | `pages/1_Market_Analysis.py` | Fail-open overwrite guard allowed MT5 live fetch to silently overwrite canonical data when row count was equal or inspection failed | P0 (Critical) | **FIXED:** Implemented strict fail-closed safeguard. Inspection errors disallow save; equal/larger row counts block silent UI overwrites. |
| DAT-01 | `src/research/data_readiness.py` | `audit_all_datasets` scanned only `*_clean.csv`, ignoring `*_validation_window.csv` and missing development/holdout contamination | P0 (Critical) | **FIXED:** Expanded scanner to audit validation windows and cross-check for timestamp overlap/leakage. |
| SIM-01 | `src/backtesting/engine.py` | Fractional lot rounding in 2R/3R split caused odd micro-lot leakage | P1 (High) | **FIXED:** Leg A & B lots allocated directly from rounded total lots; odd micro-lots preserved without loss. |

---

## 5. Frozen SMC Baseline Configuration

Canonical configuration `configs/smc_v1_frozen.json` was verified:
- **Actual SHA-256:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`
- Matches baseline expectation exactly.
- Strategy rules, parameters, and thresholds remain unoptimized and frozen.

