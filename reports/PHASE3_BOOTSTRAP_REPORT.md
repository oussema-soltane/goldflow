# Phase 3 Dependence-Aware Bootstrap Report
## Stationary Block Bootstrap & Robustness Audit on 1,124 Trades

**Date:** 2026-11-17  
**Quantitative Auditor:** Statistical Validation & Risk Engineering  
**Methodology:** Stationary Block Bootstrap (Politis & Romano, 1994) + I.I.D. Comparison  
**Resamples:** 10,000 per experiment  
**Random Seed:** 42 (Strictly Reproducible)  
**Mean Block Length:** $L = 5$ trades  
**Data Source:** `reports/PHASE3_TRADE_LEDGER.csv`  
**Machine-Readable Source:** `reports/PHASE3_BOOTSTRAP_ANALYSIS.csv`  

---

## 1. Executive Summary & Objective

In classical financial statistics, evaluating strategy profitability using a single historical equity curve or backtest metric is fundamentally vulnerable to luck, regime clustering, and sequence bias.

**Phase 3 Objective:** Subject the entire Phase 3 trade population (1,124 trades across 7 experiments) to a rigorous **10,000-resample Stationary Block Bootstrap** to establish mathematically defensible 95% confidence intervals on Profit Factor and Net Expectancy, while preserving the serial correlation of winning and losing streaks.

### Statistical Pass Criteria:
- **Primary Gate:** The **lower bound of the 95% Confidence Interval on Profit Factor must exceed 1.0** ($PF_{2.5\%} \ge 1.0$).
- **Secondary Gate:** Probability of negative expectancy must be less than 5% ($P(E \le 0) < 0.05$).

### Result:
**ALL 7 EXPERIMENTS FAILED THE PRIMARY STATISTICAL GATE.**
In every single experiment, the 95% confidence interval lower bound on Profit Factor spans below 1.0 (into net losses). The true underlying edge remains statistically unproven.

---

## 2. Comprehensive Bootstrap Results Table

| Experiment ID | Description | Sample Trades | Observed PF | Block Bootstrap 95% CI (PF) | Observed Exp ($) | Block Bootstrap 95% CI (Exp) | $P(E \le 0)$ | Statistical Verdict |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `BASELINE` | Frozen SMC v1 (Raw) | 263 | 0.963 | [0.703, 1.279] | -$1.14 | [-$9.72, +$7.91] | 60.4% | ❌ **NO EDGE** |
| `EXP_A_HTF` | HTF Bias Only | 89 | 1.007 | [0.656, 1.481] | +$0.22 | [-$11.34, +$12.76] | 50.4% | ❌ **NO EDGE** |
| `EXP_B_SESSION` | Session Filter Only | 132 | 0.917 | [0.544, 1.419] | -$2.56 | [-$15.63, +$11.44] | 65.9% | ❌ **NO EDGE** |
| `EXP_C_NEWS` | News Filter Only | 259 | 0.971 | [0.716, 1.287] | -$0.90 | [-$9.30, +$8.16] | 58.3% | ❌ **NO EDGE** |
| `EXP_F_ATR` | ATR Stops Only | 257 | 0.944 | [0.710, 1.216] | -$1.64 | [-$9.16, +$5.78] | 66.7% | ❌ **NO EDGE** |
| `EXP_H_HTF_ATR` | **HTF + ATR (Candidate)** | **88** | **1.176** | **[0.800, 1.683]** | **+$4.79** | **[-$6.04, +$16.28]** | **20.7%** | ❌ **NO EDGE** |
| `EXP_K_FULL` | Full Confluence Suite | 36 | 1.602 | [0.801, 2.790] | +$14.95 | [-$6.25, +$34.69] | 7.9% | ❌ **NO EDGE** |

---

## 3. In-Depth Statistical Analysis

### 3.1 Candidate Strategy `EXP_H_HTF_ATR` (88 Trades)
- **Observed Metrics:** On the full 17-month history, EXP_H generated +$421.59 net profit, an observed Profit Factor of 1.176, and an expectancy of +$4.79 per trade.
- **Bootstrap Uncertainty:**
  - In the worst 2.5% of bootstrap worlds, the profit factor drops to **0.800** and expectancy drops to **-$6.04** per trade.
  - In 20.7% of all 10,000 resamples (more than 1 in 5), the strategy generated a net loss over 88 trades.
- **Statistical Interpretation:** An observed PF of 1.176 over 88 trades is **insufficient to reject the null hypothesis of zero edge at the 95% confidence level ($p = 0.207 \gg 0.05$)**.

### 3.2 Full Confluence Strategy `EXP_K_FULL` (36 Trades)
- **Observed Metrics:** EXP_K generated a seemingly impressive Profit Factor of **1.602** and an expectancy of **+$14.95** per trade.
- **Bootstrap Uncertainty:**
  - Because EXP_K filters heavily, it produced only 36 trades across 17 months.
  - At $N=36$, the 95% confidence interval is extremely wide: **[0.801, 2.790]**.
  - The probability of negative expectancy is 7.9% ($p = 0.079 > 0.05$).
- **Statistical Interpretation:** While encouraging, $N=36$ trades over 17 months represents an unacceptably low trade frequency (~2 trades per month), and its confidence interval still encompasses net losses.

---

## 4. Stationary Block Bootstrap vs I.I.D. Resampling Comparison

We compared the Stationary Block Bootstrap ($L=5$) against standard I.I.D. trade resampling for `EXP_H_HTF_ATR`:

| Metric | I.I.D. Bootstrap | Stationary Block Bootstrap ($L=5$) | Impact of Autocorrelation |
|:---|:---:|:---:|:---:|
| PF 95% CI Lower Bound | 0.812 | **0.800** | Blocks widen lower tail risk |
| PF 95% CI Upper Bound | 1.665 | **1.683** | Blocks increase variance |
| Expectancy 95% CI | [-$5.82, +$15.98] | **[-$6.04, +$16.28]** | Real downside is ~4% worse |
| Probability of Net Loss | 19.8% | **20.7%** | Clustering increases loss probability |

**Methodological Takeaway:** Standard I.I.D. bootstrap underestimates downside risk and drawdowns because it breaks up sequential losing streaks. The dependence-aware block bootstrap provides an honest, institutional appraisal of tail risk.

---

## 5. Certification & Conclusion

The bootstrap audit proves conclusively that:
1. The historical profits of `SMC_CONFLUENCE_V1` are not yet statistically separated from random variance at a 95% confidence level.
2. The probability of experiencing net losses over an equivalent trading period is **20.7%**.
3. Under strict capital preservation rules, this strategy is **NOT READY FOR CAPITAL ALLOCATION**.
