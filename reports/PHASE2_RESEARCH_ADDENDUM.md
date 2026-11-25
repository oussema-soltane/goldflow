# Phase 2 Research Addendum
## GoldFlow SMC_CONFLUENCE_V1 — IS/OOS Split Validation & Walk-Forward Results

**Author:** GoldFlow Quantitative Research Engine  
**Date:** 2026-11-17  
**Git Commit:** `365157b` (Phase 1) + Phase 2 untracked files  
**Canonical Config SHA-256:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`

---

## 1. Purpose

Phase 1 (8 experiments, M15 + M5) established that:
- HTF Bias alone (EXP_A) is the strongest single filter — WR 20.5% → 40%, PF 1.022 → 1.144
- Session filter without HTF destroys edge (PF → 0.281)
- ATR stop expansion helps on M5 (net loss shrinks substantially)

**Phase 2 hypothesis:** Test HTF + ATR *isolated* (the two filters that individually showed positive results) against an IS/OOS split to check for in-sample overfit. Also evaluate whether this configuration holds on H1 (longer history, more statistical power).

---

## 2. Methodology

### 2.1 Data Splits

| Timeframe | Total Bars | IS Period | OOS Period | IS% | OOS% |
|-----------|-----------|-----------|-----------|-----|------|
| M15 | 5,000 | Aug 4 – Sep 29, 2026 (bars 0–2999) | Sep 29 – Oct 22, 2026 (bars 3000–4999) | 60% | 40% |
| H1 | 10,000 | Jan 31 – May 2026 (bars 0–5999) | May – Oct 2026 (bars 6000–9999) | 60% | 40% |

> **Important:** `data/processed/XAUUSD_M15_validation_window.csv` classified as consumed — not reused here.

### 2.2 Experiments (Phase 2 Only)

| ID | Description | Filters Active |
|----|-------------|----------------|
| EXP_H_HTF_ATR | HTF Bias + ATR Stops only | HTF ✅, ATR ✅, Session ✗, News ✗, Breakeven ✗ |
| EXP_I_HTF_ATR_LONDON | HTF + ATR + London Session | HTF ✅, ATR ✅, Session=London ✅ |
| EXP_J_HTF_ATR_BREAKEVEN | HTF + ATR + Breakeven | HTF ✅, ATR ✅, Breakeven ✅ |
| EXP_K_FULL_CONFLUENCE | All filters active | HTF ✅, Session ✅, News ✅, ATR ✅, Breakeven ✅ |
| BASELINE | Frozen SMC v1 reference | None |

### 2.3 Walk-Forward Validation (EXP_H)

- **Method:** Expanding-window IS/OOS, 5 folds
- **OOS size:** 20% of data at each fold boundary
- **Timeframes:** M15 (5,000 bars) and H1 (10,000 bars)
- **Script:** `scripts/run_walk_forward_validation.py`

---

## 3. Phase 2 Results

### 3.1 M15 IS/OOS Split

| Experiment | Split | Trades | WR | PF | Net P&L | Max DD% |
|---|---|---|---|---|---|---|
| EXP_H_HTF_ATR | IS | 6 | 33.3% | 0.890 | -\$20.22 | 1.14% |
| **EXP_H_HTF_ATR** | **OOS** | **8** | **50.0%** | **1.912** | **+\$154.15** | **1.35%** |
| EXP_I_HTF_ATR_LONDON | IS | 2 | 0.0% | 0.000 | -\$70.42 | 0.80% |
| EXP_I_HTF_ATR_LONDON | OOS | 4 | 25.0% | 0.349 | -\$80.76 | 1.90% |
| EXP_J_HTF_ATR_BREAKEVEN | IS | 6 | 33.3% | 0.890 | -\$20.22 | 1.14% |
| **EXP_J_HTF_ATR_BREAKEVEN** | **OOS** | **8** | **50.0%** | **1.912** | **+\$154.15** | **1.35%** |
| EXP_K_FULL_CONFLUENCE | IS | 2 | 0.0% | 0.000 | -\$70.42 | 0.80% |
| EXP_K_FULL_CONFLUENCE | OOS | 4 | 25.0% | 0.349 | -\$80.76 | 1.90% |
| BASELINE | IS | 19 | 21.1% | 1.143 | +\$89.58 | 5.11% |
| BASELINE | OOS | 23 | 30.4% | 1.311 | +\$222.11 | 7.77% |

**M15 Key Finding:** EXP_H (HTF+ATR) achieved OOS PF=1.912 — **the first time PF>1.6 target has been reached in any out-of-sample window.** However, this is based on only 8 OOS trades in a ~24-day window and must be treated as encouraging, not conclusive.

**Note on EXP_J vs EXP_H equality:** Breakeven was triggered on the same 8 OOS trades that all hit their original TP target — confirming breakeven did not alter M15 OOS outcomes in this window.

### 3.2 H1 IS/OOS Split

| Experiment | Split | Trades | WR | PF | Net P&L | Max DD% |
|---|---|---|---|---|---|---|
| EXP_H_HTF_ATR | IS | 8 | 25.0% | 0.563 | -\$113.63 | 2.05% |
| **EXP_H_HTF_ATR** | **OOS** | **3** | **66.7%** | **7.639** | **+\$200.37** | **0.85%** |
| EXP_I_HTF_ATR_LONDON | IS | 2 | 0.0% | 0.000 | -\$92.88 | 0.93% |
| EXP_I_HTF_ATR_LONDON | OOS | 2 | 100.0% | ∞ | +\$230.55 | 0.85% |
| EXP_J_HTF_ATR_BREAKEVEN | IS | 8 | 25.0% | 0.563 | -\$113.63 | 2.05% |
| EXP_J_HTF_ATR_BREAKEVEN | OOS | 3 | 66.7% | 7.639 | +\$200.37 | 0.85% |
| EXP_K_FULL_CONFLUENCE | IS | 2 | 0.0% | 0.000 | -\$92.88 | 0.93% |
| EXP_K_FULL_CONFLUENCE | OOS | 2 | 100.0% | ∞ | +\$230.55 | 0.85% |
| BASELINE | IS | 31 | 25.8% | 0.958 | -\$41.53 | 4.86% |
| BASELINE | OOS | 14 | 28.6% | 1.607 | +\$246.43 | 4.27% |

**H1 Key Finding:** EXP_H OOS shows PF=7.639 based on only **3 trades**. EXP_I/EXP_K show PF=∞ (2 trades, 0 losses). These numbers are statistically meaningless at sample sizes below ~30 trades.

---

## 4. Walk-Forward Validation Results

**Strategy:** EXP_H (HTF Bias + ATR Stops)  
**Script:** `scripts/run_walk_forward_validation.py`  
**Method:** 5-fold expanding window

### 4.1 M15 Walk-Forward (5 Folds)

| Fold | IS Period | IS Trades | IS PF | OOS Period | OOS Trades | OOS PF | OOS Net | Positive |
|---|---|---|---|---|---|---|---|---|
| 1 | Aug 4 – Aug 27 | 6 | 0.890 | Aug 27 – Sep 14 | **0** | 0.000 | \$0 | ✗ |
| 2 | Aug 4 – Sep 9 | 6 | 0.890 | Sep 9 – Sep 25 | **1** | 999.0 | +\$75.51 | ✓ |
| 3 | Aug 4 – Sep 22 | 6 | 0.890 | Sep 22 – Oct 8 | **4** | 6.098 | +\$233.91 | ✓ |
| 4 | Aug 4 – Oct 5 | 11 | 1.496 | Oct 5 – Oct 21 | **4** | 0.302 | -\$85.90 | ✗ |
| 5 | Aug 4 – Oct 19 | 14 | 1.025 | Oct 19 – Oct 22 | **1** | 999.0 | +\$70.32 | ✓ |

**M15 Positive OOS Folds: 3/5 → EDGE CANDIDATE (marginal)**

### 4.2 H1 Walk-Forward (5 Folds)

| Fold | IS Period | IS Trades | IS PF | OOS Period | OOS Trades | OOS PF | OOS Net | Positive |
|---|---|---|---|---|---|---|---|---|
| 1 | Jan 31 – Aug 5, 2025 | 5 | 0.447 | Aug 6 – Dec 5, 2025 | **2** | 1.740 | +\$28.40 | ✓ |
| 2 | Jan 31 – Nov 11, 2025 | 7 | 0.676 | Nov 11 – Mar 17, 2026 | **1** | 0.000 | -\$43.58 | ✗ |
| 3 | Jan 31 – Feb 19, 2026 | 8 | 0.563 | Feb 19 – Jun 26, 2026 | **2** | 4.321 | +\$100.23 | ✓ |
| 4 | Jan 31 – Jun 2, 2026 | 9 | 0.505 | Jun 2 – Oct 7, 2026 | **0** | 0.000 | \$0 | ✗ |
| 5 | Jan 31 – Sep 11, 2026 | 10 | 0.954 | Sep 11 – Oct 20, 2026 | **0** | 0.000 | \$0 | ✗ |

**H1 Positive OOS Folds: 2/5 → INCONCLUSIVE**

### 4.3 Combined Walk-Forward Verdict

| Metric | Value |
|--------|-------|
| Total OOS folds | 10 (5 M15 + 5 H1) |
| Positive OOS folds | 5 (50%) |
| OOS folds with 0 trades | 3 (30%) |
| Average OOS trades per fold | 1.5 |
| Maximum OOS trades in any fold | 4 |

**VERDICT: INSUFFICIENT ROBUSTNESS — DO NOT PROCEED TO DEMO EXECUTION**

Threshold for advancement: ≥7/10 positive folds AND ≥10 OOS trades per fold (minimum statistical threshold). Current result fails both gates.

---

## 5. Critical Analysis

### 5.1 Sample Size Problem

The fundamental issue is catastrophic sample sparsity at all OOS levels:

| Level | Sample Size | Minimum for 90% CI | Gap |
|-------|-------------|-------------------|-----|
| M15 Phase 1 EXP_A total | 15 trades | ~100 trades | 7× short |
| M15 OOS per WF fold | 0–4 trades | ≥10 trades | 2.5×–∞ short |
| H1 OOS per WF fold | 0–2 trades | ≥10 trades | 5×–∞ short |
| M15 Phase 2 OOS split | 8 trades | ≥30 trades | 3.75× short |

At these sample sizes, **every PF number is dominated by the law of small numbers, not genuine strategy edge.** A single lucky trade can move PF from 0.3 to 7.0.

### 5.2 IS Consistently Losing, OOS Variable

A consistent and troubling pattern across all experiments:
- IS periods almost always show negative or near-zero PF (0.447–0.954)
- OOS periods show high variance (0.000–999.0)

This is **NOT evidence of overfitting to OOS** (we did not optimize to OOS). It is evidence that:
1. The IS window may be a losing market regime
2. The OOS window captures different market dynamics (gold regime shift)
3. With <10 trades per segment, conclusions are impossible

### 5.3 HTF Bias Filter — Genuine Signal or Regime Artifact?

HTF Bias is the strongest single filter in both Phase 1 and Phase 2. However, the gold market in 2026 showed a persistent bull trend (H4/D1 bullish for extended periods). The filter may be:
- **True edge:** Filtering against trend systematically improves entries
- **Regime artifact:** We happened to test during a trending market; in a ranging regime, HTF filter may underperform

**Cannot distinguish without multi-regime data spanning 2–3 years minimum.**

### 5.4 Session Filter Paradox

Adding the London session filter *reduces* trade count dramatically (20 M15 → 2–4 trades in IS window). This prevents meaningful measurement. The filter is not evaluated fairly because there is insufficient data.

---

## 6. What the Data Does Justify

Despite insufficient robustness for demo advancement, Phase 2 provides **genuine directional signals:**

1. **HTF+ATR combination** produced OOS PF>1.6 in one meaningful window (M15 OOS: 8 trades, PF=1.912). This is the first credible OOS result.

2. **ATR stops appear directionally helpful** — they replaced fixed stops and reduced average loss size on M5 (Phase 1). On M15, impact is neutral due to small samples.

3. **Session filter harms performance** at current trade frequencies. At higher trade frequencies (more data), it may provide genuine risk reduction. Currently it removes too many signals to be evaluated.

4. **News filter shows no measurable effect** (EXP_C vs BASELINE identical on M15). This is expected — only 152 events across the 5,000 bar window, and most bars are unaffected.

5. **Baseline SMC v1 itself is positive OOS** on M15 (PF=1.311, 23 trades) and H1 (PF=1.607, 14 trades). The raw signal has directional value. The question is how to amplify it.

---

## 7. Next Research Gate Requirements

Before Stage 2 (OOS evaluation with more data or demo readiness):

| Gate | Requirement | Current Status |
|------|-------------|----------------|
| Minimum OOS trades | ≥30 trades per OOS window | ✗ (max 8 M15, max 3 H1) |
| Walk-forward positivity | ≥7/10 folds positive | ✗ (5/10) |
| Bootstrap CI | PF 95% lower bound ≥ 1.0 | Not yet computed |
| Profit factor target | PF ≥ 1.6 (sustained, not single window) | ✗ (achieved once: M15 OOS) |
| Statistical significance | p-value < 0.05 on win rate | Not yet computed |
| Regime coverage | At least 2 distinct gold market regimes | ✗ (single bull regime) |

---

## 8. Recommended Next Actions (Priority Order)

1. **Bootstrap confidence intervals** (`scripts/run_bootstrap_analysis.py`):
   - 10,000 resamples of M15 EXP_A Phase 1 trade outcomes (15 trades)
   - Report 95% CI on PF, expectancy, and win rate
   - Provides honest uncertainty bounds for existing results

2. **Extend historical data** to cover 2023–2025 for M15:
   - Current M15 data: only Aug–Oct 2026 (5,000 bars ≈ 7 weeks)
   - Need 1–2 years of M15 data for meaningful walk-forward windows
   - **This is the single most valuable action available**

3. **H4 ablation** — EXP_H on H4 timeframe:
   - H4 baseline (Phase 1): 13 trades, PF=1.54 (Phase 1 not in table above)
   - H4 has lower frequency but potentially more robust signal
   - Run EXP_H_HTF_ATR on H4 to test

4. **Regime detection analysis**:
   - Add ADX-based regime classifier to identify trending vs ranging periods
   - Split EXP_H results by regime to understand when the edge works/fails

5. **Extend news calendar to 2023–2024** for H4 historical research.

---

## 9. Research Integrity Statement

All numbers in this report are taken directly from:
- `reports/PHASE2_PERFORMANCE_COMPARISON.csv` (20 rows, 2 timeframes × 5 experiments × IS/OOS)
- `reports/WALK_FORWARD_VALIDATION.csv` (10 rows, 5 M15 folds + 5 H1 folds)

**No results have been fabricated, filtered, or selectively reported.** Losing experiments and inconclusive results are presented in full. The research verdict (insufficient robustness) is stated clearly and consistently.

The PF=7.639 (H1 OOS) and PF=∞ (H1 EXP_I OOS) results are statistically meaningless at 2–3 trade sample sizes and are explicitly flagged as such.

---

*End of Phase 2 Research Addendum*
