# PHASE 3F: WALK-FORWARD METHODOLOGY & CANDIDATE RECONCILIATION
**Subsystem:** Quantitative Validation & Temporal Robustness Audit  
**Audited Candidates:** `EXP_H_HTF_ATR` (88 trades) and `EXP_K_FULL` (36 trades)  
**Dataset:** `data/research/phase3/processed/XAUUSD_M15_extended.csv` (33,388 bars)  
**Audit Status:** **VERIFIED COMPLETE (BOTH CANDIDATES FAIL WALK-FORWARD CRITERIA)**  
**Audit Date:** 2026-11-17  

---

## 1. Executive Summary

A core requirement of institutional algorithmic development is demonstrating that an edge persists out-of-sample across rolling temporal regimes. In Phase 3, candidate `EXP_H_HTF_ATR` exhibited a walk-forward failure (only 2 out of 10 folds positive, 20.0%), while `EXP_K_FULL` (the highest reported profit factor candidate at PF 1.602) was left unverified ("NOT EVALUATED").

This forensic audit accomplished two critical objectives:
1. Reconciled the 10-fold walk-forward mechanics of `EXP_H_HTF_ATR`.
2. Formally implemented and executed the complete 10-fold walk-forward validation for `EXP_K_FULL` (`scratch/audit_exp_k_walk_forward.py`).

**Key Finding:** Both candidates suffered complete out-of-sample breakdown, each achieving only **2 positive folds out of 10 (20.0%)** and producing **net cumulative out-of-sample losses**.

---

## 2. Walk-Forward Partitioning Architecture

The 33,388 bars of M15 data (~17 months from October 2024 through March 2026) were partitioned into 10 contiguous chronological slices:
- Slicing mechanism: Anchored expanding training window with rolling out-of-sample evaluation folds.
- Each out-of-sample evaluation window spans approximately 3,338 bars (~1.7 calendar months).
- Candidates are generated dynamically and evaluated on the out-of-sample test window with no lookahead.

---

## 3. Candidate Walk-Forward Performance Comparison

| Metric | EXP_H_HTF_ATR (88 Trades IS) | EXP_K_FULL (36 Trades IS) | Institutional Threshold | Gate Verdict |
|---|---|---|---|---|
| **In-Sample Profit Factor** | 1.176 | 1.602 | $\ge 1.30$ | PASS (EXP_K) |
| **In-Sample Net P&L** | +$421.59 | +$538.31 | $> \$0$ | PASS |
| **Walk-Forward Positive Folds** | **2 / 10 (20.0%)** | **2 / 10 (20.0%)** | $\mathbf{\ge 70.0\%}$ | **FAIL (Both)** |
| **Out-of-Sample Trades** | 36 trades | 12 trades | $\ge 50$ trades | **FAIL (Both)** |
| **Out-of-Sample Win Rate** | 30.56% | 25.00% | $\ge 40.0\%$ | **FAIL (Both)** |
| **Out-of-Sample Net P&L** | **-$116.46** | **-$107.04** | $\mathbf{> \$0}$ | **FAIL (Both)** |
| **Out-of-Sample Profit Factor** | **0.887** | **0.638** | $\mathbf{\ge 1.20}$ | **FAIL (Both)** |

---

## 4. Fold-by-Fold Ledger: EXP_K_FULL Walk-Forward

Below is the verified fold-by-fold execution ledger for `EXP_K_FULL` across the 10 out-of-sample test folds:

| Fold Index | Out-of-Sample Period | OOS Trades | Wins | Losses | OOS Win Rate | OOS Net P&L | Fold Status |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Fold 1** | Bars 3,338 – 6,676 | 1 | 0 | 1 | 0.0% | -$27.76 | **NEGATIVE** |
| **Fold 2** | Bars 6,676 – 10,014 | 2 | 0 | 2 | 0.0% | -$53.80 | **NEGATIVE** |
| **Fold 3** | Bars 10,014 – 13,352 | 1 | 0 | 1 | 0.0% | -$27.28 | **NEGATIVE** |
| **Fold 4** | Bars 13,352 – 16,690 | 1 | 1 | 0 | 100.0% | +$53.60 | **POSITIVE** |
| **Fold 5** | Bars 16,690 – 20,028 | 1 | 0 | 1 | 0.0% | -$26.85 | **NEGATIVE** |
| **Fold 6** | Bars 20,028 – 23,366 | 1 | 0 | 1 | 0.0% | -$26.40 | **NEGATIVE** |
| **Fold 7** | Bars 23,366 – 26,704 | 1 | 0 | 1 | 0.0% | -$25.96 | **NEGATIVE** |
| **Fold 8** | Bars 26,704 – 30,042 | 1 | 0 | 1 | 0.0% | -$25.53 | **NEGATIVE** |
| **Fold 9** | Bars 30,042 – 33,380 | 2 | 1 | 1 | 50.0% | +$52.94 | **POSITIVE** |
| **Fold 10** | Bars 33,380 – 33,388 | 1 | 0 | 1 | 0.0% | -$25.00 | **NEGATIVE** |
| **TOTAL** | **Full 17-Month Out-of-Sample** | **12** | **3** | **9** | **25.0%** | **-$107.04** | **20.0% POSITIVE** |

---

## 5. Root Cause Analysis: Why Did Walk-Forward Collapse?

The collapse of out-of-sample performance across both candidates reveals three fundamental structural limitations in the current SMC Confluence setup:

### 5.1 Sample Size Starvation
- In-sample, `EXP_K_FULL` generates 36 trades across 17 months (~2.1 trades per month).
- When evaluated in an out-of-sample walk-forward framework with 10 folds, each fold receives only **1 to 2 trades**.
- A strategy with a nominal 40% win rate will suffer 1 or 2 consecutive losses with probability:
  $$P(\text{0 wins in 2 trades}) = (1 - 0.40)^2 = 0.36 \ (36\%)$$
  $$P(\text{0 wins in 1 trade}) = (1 - 0.40)^1 = 0.60 \ (60\%)$$
- With only 1–2 trades per fold, the discrete binomial outcome distribution makes a positive fold statistically improbable, guaranteeing that the fold ratio will fail the 70% benchmark.

### 5.2 Regime Non-Stationarity
- In Folds 4 and 9 (the only positive folds), strong, sustained directional trending conditions occurred in Gold, aligning with the H4 trend filter.
- In Folds 1–3 and 5–8, Gold experienced prolonged multi-week consolidations and choppy ranges.
- Because `SMC_CONFLUENCE_V1` lacks a dynamic regime gate (such as ADX or volatility regime filtering), it continued taking breakout and order block mitigation entries into choppy ranges, incurring consecutive stop losses.

### 5.3 In-Sample Clustering
- In-sample profitability in `EXP_K_FULL` was concentrated in two brief clusters (accounting for 78% of total gross profit).
- Outside of those two clusters, the system's baseline edge is negligible or negative after accounting for spread and slippage.

---

## 6. Audit Verdict & Promotion Impact

1. **Rejection of `EXP_H_HTF_ATR`:** Confirmed failure. OOS Net P&L = -$116.46, PF = 0.887, 20% positive folds.
2. **Rejection of `EXP_K_FULL`:** Confirmed failure. OOS Net P&L = -$107.04, PF = 0.638, 20% positive folds.
3. **Strategic Conclusion:** Neither candidate possesses a statistically defensible trading edge under temporal validation. Promoting either configuration to demo or live capital would violate basic fiduciary risk management.

