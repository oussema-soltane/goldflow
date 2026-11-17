# PHASE 3F: BOOTSTRAP RESAMPLING METHODOLOGY AUDIT
**Subsystem:** Quantitative Statistical Inference, Confidence Intervals & Tail Risk Audit  
**Audited Candidates:** `EXP_H_HTF_ATR` ($N=88$ trades) and `EXP_K_FULL` ($N=36$ trades)  
**Resampling Budget:** 120,000 Total Resamples (20,000 iterations $\times$ 6 block lengths)  
**Audit Status:** **VERIFIED COMPLETE (FAILED STATISTICAL SIGNIFICANCE BENCHMARKS)**  
**Audit Date:** 2026-11-17  

---

## 1. Executive Summary

Standard backtests present a single historical realization of a trading strategy, obscuring how much of the performance is attributable to luck vs true statistical edge. Bootstrap resampling estimates the true underlying sampling distribution of key performance indicators (such as Profit Factor and Expectancy) without relying on strict Gaussian normality assumptions.

This audit conducted an exhaustive stationary block bootstrap sensitivity analysis across block lengths $L \in \{1, 3, 5, 10, 15, 20\}$ to test the statistical persistence of GoldFlow candidates under varying autocorrelation and volatility clustering assumptions.

**Core Finding:** Neither `EXP_H_HTF_ATR` nor `EXP_K_FULL` achieves statistical significance at the $\alpha = 0.05$ significance level. Across all standard block lengths, the 95% Confidence Interval for Profit Factor spans values below 1.0, and the empirical probability of realizing a net loss over an 88-trade lifecycle exceeds 17%.

---

## 2. Stationary Block Bootstrap Sensitivity Analysis

### 2.1 Candidate `EXP_H_HTF_ATR` ($N = 88$ trades, Observed $\text{PF} = 1.176$, Expectancy = \$4.79)
Parametric One-Tailed $t$-Test ($H_0: \mu \le 0$ vs $H_1: \mu > 0$): $t = 0.685, p = 0.2475$ (Fail to reject $H_0$).

| Block Length $L$ | Resampling Architecture | PF 95% CI Lower | PF Median | PF 95% CI Upper | Expectancy 95% CI | Empirical $P(\text{Net} \le 0)$ | CI Lower $> 1.0$ |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **$L=1$** | I.I.D. Resampling | 0.728 | 1.177 | 1.818 | [-$8.47, +$18.69] | 24.5% | **FAIL** |
| **$L=3$** | Stationary Block | 0.777 | 1.172 | 1.705 | [-$6.85, +$16.67] | 21.8% | **FAIL** |
| **$L=5$** | Stationary Block | 0.806 | 1.170 | 1.692 | [-$5.90, +$16.60] | 20.9% | **FAIL** |
| **$L=10$** | Stationary Block | 0.822 | 1.164 | 1.666 | [-$5.37, +$16.01] | 20.3% | **FAIL** |
| **$L=15$** | Stationary Block | 0.842 | 1.168 | 1.651 | [-$4.76, +$15.66] | 19.8% | **FAIL** |
| **$L=20$** | Stationary Block | 0.851 | 1.176 | 1.640 | [-$4.45, +$15.41] | 17.9% | **FAIL** |

### 2.2 Candidate `EXP_K_FULL` ($N = 36$ trades, Observed $\text{PF} = 1.602$, Expectancy = \$14.95)
Parametric One-Tailed $t$-Test ($H_0: \mu \le 0$ vs $H_1: \mu > 0$): $t = 1.226, p = 0.1141$ (Fail to reject $H_0$).

| Block Length $L$ | Resampling Architecture | PF 95% CI Lower | PF Median | PF 95% CI Upper | Expectancy 95% CI | Empirical $P(\text{Net} \le 0)$ | CI Lower $> 1.0$ |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **$L=1$** | I.I.D. Resampling | 0.749 | 1.593 | 3.170 | [-$7.93, +$39.23] | 10.5% | **FAIL** |
| **$L=3$** | Stationary Block | 0.747 | 1.606 | 2.994 | [-$7.91, +$37.38] | 9.9% | **FAIL** |
| **$L=5$** | Stationary Block | 0.797 | 1.620 | 2.790 | [-$6.33, +$34.66] | 7.7% | **FAIL** |
| **$L=10$** | Stationary Block | 0.906 | 1.602 | 2.599 | [-$2.85, +$31.35] | 4.7% | **FAIL** |
| **$L=15$** | Stationary Block | 0.967 | 1.602 | 2.507 | [-$1.00, +$30.19] | 3.2% | **FAIL** |
| **$L=20$** | Stationary Block | 1.007* | 1.602 | 2.419 | [+$0.21, +$28.99] | 2.4% | *Borderline |

*\*Methodological Note on $L=20$ for `EXP_K_FULL`: With a total sample size of $N=36$ trades, a block size of $L=20$ trades exceeds 55% of the entire sample. Sampling blocks of length 20 from a 36-trade sequence violates asymptotic stationarity assumptions, effectively duplicating almost the entire trade history and artificially compressing confidence intervals. Under all valid block lengths ($L \le 10$, where $L < N/3$), the lower bound is strictly below 1.0.*

---

## 3. Quantitative Risk & Asymmetry Findings

### 3.1 Failure to Reject the Zero-Edge Null Hypothesis
- For `EXP_H_HTF_ATR`, the probability of observing its +$4.79/trade expectancy purely by random chance from a zero-edge strategy is **24.75%** ($p = 0.2475$).
- For `EXP_K_FULL`, the probability of observing its +$14.95/trade expectancy by random chance is **11.41%** ($p = 0.1141$).
- Neither candidate achieves statistical significance ($p < 0.05$). Under institutional peer review, these results are classified as **statistically indistinguishable from random noise**.

### 3.2 High Probability of Net Capital Destruction
- In `EXP_H_HTF_ATR`, an investor deploying the strategy across an 88-trade campaign faces an empirical **17.9% to 24.5% probability of ending with a net dollar loss**, even with zero execution slippage degradation.
- The 95% Confidence Interval for expectancy extends into negative territory (down to -$8.47 per trade).

### 3.3 Drawdown & Streak Clustering
- In `EXP_H_HTF_ATR`, the single-trade loss probability ($1 - \text{WR}$) is **62.5%**. The maximum observed losing streak was **7 consecutive losses**.
- In `EXP_K_FULL`, the single-trade loss probability is **58.3%**. The maximum observed losing streak was **5 consecutive losses**.
- In stationary block resampling ($L \ge 5$), losing streaks routinely cluster into drawdown sequences exceeding 12% to 18% of initial capital.

---

## 4. Methodological Audit of `src/backtesting/engine.py`

The bootstrap function `compute_bootstrap_pf_ci` in `src/backtesting/engine.py` was inspected:
- Current implementation uses uniform random replacement over individual trade P&Ls (I.I.D. bootstrap).
- **Critique:** I.I.D. resampling assumes that trade returns are identically and independently distributed. In reality, market returns exhibit volatility clustering and regime autocorrelation.
- **Recommendation for SMC_CONFLUENCE_V2:** Replace the I.I.D. bootstrap in `engine.py` with a **Politis & Romano (1994) Stationary Block Bootstrap** using geometric block lengths parameterized around expected streak lengths ($p = 1/L$, where $L = 5$).

---

## 5. Audit Verdict & Promotion Impact

1. **Bootstrap Gate Requirement:** An institutional candidate must demonstrate a 95% CI lower bound for Profit Factor $> 1.000$ and $p < 0.05$ under stationary block resampling.
2. **Audit Verdict:**
   - `EXP_H_HTF_ATR`: **FAILED** (95% CI Lower = 0.806 at $L=5$, $p = 0.2475$).
   - `EXP_K_FULL`: **FAILED** (95% CI Lower = 0.797 at $L=5$, $p = 0.1141$).
3. **Promotion Impact:** Neither strategy can be approved for live capital or demo trading based on bootstrap validation.

