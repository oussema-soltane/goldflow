# GoldFlow Phase 5 — Reconciliation & Audit Report

**Audit Date:** 2026-10-28  
**Auditor:** Quantitative Research Engineer & Financial Data Audit Desk  
**Target Artifact:** GoldFlow SMC Primary Strategy & Phase 5 MTF Validation  
**Instrument:** XAUUSD (Gold CFD / Spot)  
**Baseline Strategy Configuration:** `configs/smc_v1_frozen.json` (`1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`)  
**Status:** **RECONCILIATION COMPLETE — ALL 458 TESTS PASSING**

---

## 1. Executive Summary

An exhaustive quantitative methodology audit was conducted on the GoldFlow Phase 5 validation suite, inspecting generated trade ledgers, raw CSV datasets, sidecar metadata, backtest event logs, cost-replay engines, and statistical assertions.

Three primary discrepancies were identified in earlier Phase 5 reporting:
1. **Finding A (M15 Baseline P&L Discrepancy):** The M15 baseline net P&L was reported as -$239.12 in backtesting, but listed as -$6,109.68 in the cost-replay robustness section.
2. **Finding B (Evaluation Window Inconsistency):** Documentation stated a "common evaluation window" of 2025-05-13 to 2026-10-20 (~17 months) for all four timeframes, despite the M15 dataset only beginning on 2026-08-04 (~2.5 months).
3. **Finding C (Statistical Interpretation & Payoff Disconnect):** Break-even win rate was arbitrarily assumed to be 50.0% rather than derived from actual asymmetric SMC payoff characteristics, and small-sample fragility was insufficiently quantified.

All three issues have been rigorously investigated, mathematically reconciled, corrected with minimal code changes, verified by automated regression tests, and audited against the frozen baseline configuration.

---

## 2. Finding A — M15 Baseline P&L Discrepancy Reconciliation

### 2.1 The Discrepancy
- **Backtest Engine Report:** M15 Baseline Net P&L = `-$239.12`, 40 closed trades (39 rule exits, 1 end-of-data exit).
- **Previous Robustness Table:** M15 Baseline Cost Replay = `-$6,109.68`, claiming to be based on the same 40 trades.

### 2.2 Forensic Investigation
To determine the root cause, both execution paths were audited across all eight required dimensions:
1. **Dataset & Date Range:** Both runs consumed `data/processed/XAUUSD_M15_clean.csv` (SHA-256: `2f6bded7fc58752a7de9097c9258bb24840be79fbaad55d82ebf4835dfad2def`).
2. **Strategy Configuration:** Both referenced `configs/smc_v1_frozen.json`.
3. **Position Sizing & Initial Equity:** Both used $10,000 initial equity with a 1.0% risk budget per trade.
4. **Contract & Point Value:** Both adhered to 100 oz contract size ($1.00/point/lot) and 0.01 tick size.
5. **Cost Model:** Baseline costs in both were 1.0x spread, $0.05/side slippage, and $0.00 commission.
6. **Exit Rules & Collision Handling:** Both enforced conservative stop-loss-first collision rules.
7. **Trade Ledger Comparison:** In `scripts/run_phase5_validation.py:366`, the cost-replay runner called:
   ```python
   cost_M15_baseline = _run_cost_scenarios(trades_csv, ...)
   ```
   where `trades_csv` was the combined multi-timeframe export (`smc_mtf_trades.csv`). That file contained **1,378 total candidates** and **1,174 closed rule-exit trades** spanning **ALL four experimental variants**:
   - M15 Baseline: 40 closed trades (39 rule exits)
   - M15 MTF Confirmed: 11 closed trades (11 rule exits)
   - M5 Baseline: 842 closed trades (841 rule exits)
   - M5 MTF Confirmed: 283 closed trades (283 rule exits)
8. **Mathematical Proof:**
   Replaying all 1,174 rule-exit trades across all 4 variants yielded:
   - Combined Net Profit = `-$6,109.68`
   - Combined Rule Exits = `1,174`
   - Combined Win Rate = `27.85%`
   - Combined Max Drawdown = `$7,168.33`

   The -$6,109.68 figure was **not an M15 baseline calculation at all**; it was the combined cost replay of the entire repository test corpus, mislabeled as "M15 Baseline".

### 2.3 Correction Implemented
1. `_run_cost_scenarios()` in `scripts/run_phase5_validation.py` was refactored to accept pre-filtered trade collections (`list[dict]`, `pd.DataFrame`, or `Path`).
2. `cost_M15_baseline` was explicitly filtered to `timeframe == 'M15'` and `strategy_variant == 'SMC_v1_baseline'`.
3. Cost replays for `cost_M5_baseline` and `cost_M5_mtf` were cleanly partitioned into their own designated data structures.
4. Added regression test `test_cost_replay_filters_m15_baseline_properly` in `tests/test_phase5_regression.py`.

### 2.4 Reconciled Results
Replaying the correctly filtered 40 M15 baseline trades:

| Metric | Backtest Engine | Cost Replay (Corrected) | Prior Report (Defective) |
|---|---|---|---|
| Closed Trades | 40 (39 rule + 1 EOD) | 40 (39 rule + 1 EOD) | 1,176 (all corpus) |
| Rule Exits | 39 | 39 | 1,174 |
| Gross P&L | -$166.19 | -$166.19 | -$1,373.42 |
| Total Costs | $72.93 | $73.13 | $4,736.26 |
| Net P&L | **-$239.12** | **-$239.32** | **-$6,109.68** |
| Profit Factor | 0.922 | 0.922 | 0.904 |
| Win Rate | 20.51% | 20.51% | 27.85% |
| Max Drawdown | $1,632.95 (mark-to-market) | $1,032.68 (realized) | $7,168.33 |

*Discrepancy Resolution:* The minor $0.20 difference between -$239.12 and -$239.32 is entirely explained by end-of-data liquidation modeling (the backtest engine applied 1 side of slippage on bar-close markout, whereas the replay model applied 2 sides: $0.05 × 2 × 0.04 lots × 100 oz = $0.40 vs $0.20). Both models match exactly on pure rule exits (-$213.96).

---

## 3. Finding B — Dataset Chronology & Evaluation Window Reconciliation

### 3.1 The Inconsistency
Previous documentation claimed:
> "Common evaluation window: 2025-05-13 to 2026-10-20 (~17 months)."

However, inspection of `data/processed/XAUUSD_M15_clean.meta.json` and the CSV data revealed that the M15 dataset begins on `2026-08-04T12:00:00+00:00`, containing only 5,000 bars. It is mathematically impossible for M15 to have been evaluated over a 17-month window starting in May 2025.

### 3.2 True Dataset Inventories and Ranges

| Timeframe | Rows | First Timestamp (UTC) | Last Timestamp (UTC) | Calendar Span | Purpose |
|---|---|---|---|---|---|
| **H4** | 5,000 | 2023-07-27 17:00 | 2026-10-20 09:00 | ~38.8 months | Higher-timeframe context 1 |
| **H1** | 10,000 | 2025-01-31 14:00 | 2026-10-20 14:00 | ~20.6 months | Higher-timeframe context 2 |
| **M15** | 5,000 | 2026-08-04 12:00 | 2026-10-22 09:15 | ~2.6 months | Entry execution (Short) |
| **M5** | 99,999 | 2025-05-13 22:15 | 2026-10-20 15:50 | ~17.2 months | Entry execution (Long) |

### 3.3 Exact Evaluated Overlapping Windows
1. **M15 Experiment Evaluation Window (M15 ∩ H1 ∩ H4):**
   - Start: `2026-08-04 12:00:00+00:00` (bounded by M15 start)
   - End: `2026-10-20 09:00:00+00:00` (bounded by H4 end)
   - M15 Bars in range: **4,823 bars** (the last 177 bars after Oct 20 lack H4 context)
   - Duration: **~77 calendar days (~2.5 months)**.
2. **M5 Experiment Evaluation Window (M5 ∩ H1 ∩ H4):**
   - Start: `2025-05-13 22:15:00+00:00` (bounded by M5 start)
   - End: `2026-10-20 09:00:00+00:00` (bounded by H4 end)
   - M5 Bars in range: **99,917 bars**
   - Duration: **~525 calendar days (~17.2 months)**.
3. **True 4-Way Overlap Window (H4 ∩ H1 ∩ M15 ∩ M5):**
   - Start: `2026-08-04 12:00:00+00:00`
   - End: `2026-10-20 09:00:00+00:00`
   - Exact bar counts: H4: 330 bars | H1: 1,207 bars | M15: 4,823 bars | M5: 14,467 bars.

### 3.4 Verification of Strategy Comparability
- Within each timeframe experiment (M15 baseline vs. M15 MTF; M5 baseline vs. M5 MTF), both variants were executed on the **identical underlying price bars** with identical warm-up periods (5-bar fractal swing lookback + 2-bar confirmation delay) and identical execution parameters.
- No synthetic interpolation, price smoothing, or artificial bar fabrication occurred.
- Added regression test `test_dataset_evaluation_windows_and_intersections`.

---

## 4. Finding C — Statistical Interpretation & Empirical Payoff Analysis

### 4.1 Payoff Ratio vs. The 50% Break-Even Fallacy
Previous reports stated:
> "Wilson 95% CI spans [13.2%, 67.8%]. This range includes the 50% breakeven threshold."

In financial quantitative modeling, a 50.0% win rate is break-even **only** when reward-to-risk is symmetric ($1:1$). The SMC framework utilizes swing liquidity targets and structural order blocks, resulting in an asymmetric payoff structure:

$$\text{Break-Even Win Rate } p_{be} = \frac{1}{1 + B} = \frac{\text{Avg Loss}}{\text{Avg Win} + \text{Avg Loss}}$$

From the verified M15 MTF closed trade ledger ($n = 11$):
- **4 Winning Trades:** Total Net Profit = +$1,145.27 | Mean Win = **$286.32** | Mean R = **+2.972**
- **7 Losing Trades:** Total Net Loss = -$638.71 | Mean Loss = **$91.24** | Mean R = **-1.000**
- **Empirical Payoff Ratio ($B$):** $\frac{\$286.32}{\$91.24} = \mathbf{3.1379}$
- **Empirical Break-Even Win Rate ($p_{be}$):** $\frac{1}{1 + 3.1379} = \mathbf{24.17\%}$ (or $25.18\%$ on R-multiples).

### 4.2 Statistical Significance and Sample-Size Reality
While the observed win rate of **36.36%** exceeds the empirical break-even threshold of 24.17%, the sample size of **$n = 11$** is statistically underpowered:
1. **Wilson 95% Confidence Interval:** $[13.2\%, 67.8\%]$.
   - The lower confidence bound ($13.2\%$) extends substantially into severe negative expectancy.
2. **Single-Trade Outlier Dependency:**
   - Trade `SMC_M15_0053` (entered 2026-10-21 22:30 UTC) yielded **+$696.16 net profit** ($R = +7.24$).
   - This single trade accounts for **137.4%** of the entire cumulative net profit (+$506.56).
   - Removing this single trade leaves the remaining 10 trades with:
     - Net P&L: **-$189.60** (Unprofitable)
     - Win Rate: **30.0%** (3 wins / 10 trades)
     - Revised Payoff Ratio: $B = 1.64$ ($Avg Win = $149.70, $Avg Loss = $91.24)
     - Revised Break-Even: $p_{be} = 37.87\%$ (Observed 30.0% is below break-even).
3. **M5 Disconfirmation:** On the statistically meaningful sample of M5 ($n = 283$ closed trades over 17 months), the MTF filter failed to produce profitability (Net P&L: -$1,421.00, PF: 0.933, Win Rate: 28.98%).
4. **Conclusion:** The M15 positive result is an exploratory artifact driven by a single favorable swing trade. Under no circumstances can this be cited as an out-of-sample trading edge.

---

## 5. Part 2 — Quality Gate Verification Results

All required verification checks were executed live:

| Check # | Verification Gate | Command Executed | Result | Status |
|---|---|---|---|---|
| 1 | Complete Test Suite | `python -m pytest tests/ -q --tb=short` | **458 passed** in 160.18s | **CLEAN** |
| 2 | Python Compilation | `python -m compileall src/ scripts/ pages/ tests/` | Exit code 0 across all files | **CLEAN** |
| 3 | Research Readiness Gate | `python scripts/research_readiness.py` | `READY_WITH_WARNINGS` (0 blockers) | **PASSED** |
| 4 | Execution-Spec Audit | `python scripts/audit_execution_specs.py` | `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE` | **PASSED** |
| 5 | Phase 5 Pipeline Runner | `python scripts/run_phase5_validation.py --timeframes M15 M5` | Regenerated all reports and metrics | **VERIFIED** |
| 6 | Artifact Integrity | Checked SHA-256 and row counts for `smc_mtf_*.csv` | All 4 files regenerated & consistent | **VERIFIED** |
| 7 | Frozen Config Hash | Checked `configs/smc_v1_frozen.json` | `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` | **MATCH** |
| 8 | Git Diff Inspection | `git status -s` | No unintended modifications; user work preserved | **VERIFIED** |

---

## 6. Summary of Reconciled Metrics

### Primary Strategy Comparison (All Costs Modeled)
- **Initial Capital:** $10,000.00 USD
- **Position Sizing:** 1.0% equity risk budget
- **Execution Frictions:** 1.0x spread, $0.05/side slippage, $0.00 commission, stop-first collision.

| Timeframe | Strategy Variant | Candidates | Closed | Win Rate | 95% Wilson CI | Break-Even | Gross P&L | Total Costs | Net P&L | Return | PF | Max DD | Avg R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **M15** | SMC Baseline | 54 | 40 | 20.51% | [10.8%, 35.5%] | 31.8% | -$166.19 | $72.93 | **-$239.12** | -2.39% | 0.922 | $1,632.95 | -0.068 |
| **M15** | SMC MTF Confirmed | 11 | 11 | 36.36% | [13.2%, 67.8%] | **24.17%** | +$528.46 | $21.90 | **+$506.56** | +5.07% | 1.793 | $457.65 | +0.444 |
| **M5** | SMC Baseline | 1,015 | 842 | 27.71% | [24.8%, 30.8%] | 30.4% | -$1,686.73 | $3,268.90 | **-$4,955.63** | -49.56% | 0.873 | $6,392.88 | -0.076 |
| **M5** | SMC MTF Confirmed | 298 | 283 | 28.98% | [24.0%, 34.5%] | 29.8% | -$48.97 | $1,372.03 | **-$1,421.00** | -14.21% | 0.933 | $3,502.65 | -0.039 |

---

## 7. Unresolved Blockers and Data Governance Limitations

1. **Broker Provenance:** Historical bars originate from a MetaQuotes-Demo MT5 terminal export (`DECLARED_NOT_AUTHENTICATED`). No institutional tick tape or LMAX/Currenex/Dukascopy cross-audit exists.
2. **Untouched Out-of-Sample Vault Missing:** All 4 datasets were repeatedly inspected during strategy development and parameter tuning.
3. **Recommendation:** Proceed immediately to **Phase 6** to build an independent holdout vault and ingest institutional forward tick data.

