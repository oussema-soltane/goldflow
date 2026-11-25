# PHASE 3I: STATISTICAL METHODOLOGY & INFERENCE AUDIT
**Subsystem:** Quantitative Statistics, Confidence Intervals & Hypothesis Testing  
**Auditor:** Lead Quantitative Research Engineer & Independent Statistical Auditor  
**Audit Status:** **METHODOLOGY AUDITED & EPISTEMOLOGICAL CLASSIFICATIONS CERTIFIED**  
**Audit Date:** 2026-11-17  

---

## 1. Executive Summary

A critical weakness in algorithmic trading research is the conflation of statistical terms—such as treating an empirical bootstrap loss frequency as a conventional $p$-value, or assuming that failure to reject a null hypothesis mathematically proves the absence of an edge.

This audit establishes a rigorous, transparent statistical taxonomy for all inference tools utilized across GoldFlow, detailing the exact null hypotheses, degrees of freedom, resampling algorithms, and mathematical limitations of each reported metric.

---

## 2. Statistical Procedure Specifications

### 2.1 Parametric Student's $t$-Test for Positive Strategy Expectancy
Used to test whether average trade net P&L is statistically greater than zero.

1. **Null Hypothesis ($H_0$):** $\mu \le 0$ (The strategy has zero or negative expected return per trade).
2. **Alternative Hypothesis ($H_1$):** $\mu > 0$ (The strategy has positive expected return per trade).
3. **Input Observations:** Vector of individual trade net P&Ls, $X = [x_1, x_2, \dots, x_N]$.
4. **Test Statistic:** 
   $$t = \frac{\bar{X} - 0}{s / \sqrt{N}}$$
   where $\bar{X} = \frac{1}{N}\sum x_i$, and $s = \sqrt{\frac{1}{N-1}\sum (x_i - \bar{X})^2}$.
5. **Degrees of Freedom:** $df = N - 1$ ($df = 87$ for `EXP_H`; $df = 35$ for `EXP_K`).
6. **Test Directionality:** Strictly **One-Sided** (directional edge test, $H_1: \mu > 0$).
7. **Dependence Assumptions:** Assumes trade returns are independent and identically distributed (I.I.D.) with finite variance. If serial correlation or volatility clustering exists, standard errors are underestimated and $t$-statistics are inflated.
8. **Observed Results:**
   - `EXP_H_HTF_ATR` ($N=88$): $t = 0.685, p = 0.2475$. Fail to reject $H_0$.
   - `EXP_K_FULL` ($N=36$): $t = 1.226, p = 0.1141$. Fail to reject $H_0$.

---

### 2.2 Stationary Block Bootstrap for Profit Factor Confidence Intervals
Used to estimate the sampling distribution of Profit Factor while accounting for autocorrelation and volatility clustering in sequential trades.

1. **Estimator:**
   $$\widehat{\text{PF}} = \frac{\sum_{i=1}^N x_i \cdot \mathbb{I}(x_i > 0)}{\sum_{i=1}^N |x_i| \cdot \mathbb{I}(x_i < 0)}$$
2. **Resampling Algorithm:** Politis & Romano (1994) Stationary Block Bootstrap.
   - Block length $L$ is geometrically distributed with mean $L_{\text{mean}} = 5$ (continuation probability $1 - p = 1 - 1/L_{\text{mean}} = 0.80$).
   - The trade series is wrapped circularly to guarantee stationarity.
3. **Resample Budget ($B$):** $B = 10,000$ resampled paths per evaluation.
4. **Random Seed:** `numpy.random.default_rng(42)`.
5. **Handling of Zero-Loss Resamples:** If a resampled path contains zero gross losses, Profit Factor is bounded at $100.0$ (or $999.0$) to avoid infinite division anomalies.
6. **Confidence Interval Construction:** Empirical Percentile Method at $\alpha = 0.05$ (95% two-sided CI):
   $$\text{CI}_{95\%} = \left[ \widehat{q}_{0.025}, \ \widehat{q}_{0.975} \right]$$
7. **Observed Results ($L=5$):**
   - `EXP_H_HTF_ATR`: 95% CI = $[0.806, \ 1.692]$. Lower bound $< 1.000$ (**FAILS GATE**).
   - `EXP_K_FULL`: 95% CI = $[0.797, \ 2.790]$. Lower bound $< 1.000$ (**FAILS GATE**).

---

## 3. Strict Demarcation of Statistical Concepts

To prevent ambiguity, GoldFlow research reports must never conflate the following four distinct metrics:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   TAXONOMY OF RESEARCH METRICS                         │
├────────────────────────────────┬───────────────────────────────────────┤
│ Concept                        │ What It Actually Measures             │
├────────────────────────────────┼───────────────────────────────────────┤
│ 1. Bootstrap Confidence        │ The sampling uncertainty of the       │
│    Interval (e.g. PF CI)       │ estimator due to finite sample size.  │
├────────────────────────────────┼───────────────────────────────────────┤
│ 2. Empirical Negative-Net      │ The proportion of resampled paths     │
│    Frequency P(Net <= 0)       │ where cumulative net return <= $0.    │
│                                │ (A path-level loss probability).      │
├────────────────────────────────┼───────────────────────────────────────┤
│ 3. Conventional Student's      │ The probability of observing sample   │
│    t-test p-value              │ mean >= Xbar under the null (mu <= 0).│
├────────────────────────────────┼───────────────────────────────────────┤
│ 4. Single-Trade Loss           │ The empirical frequency of losing     │
│    Probability (1 - WR)        │ trades (e.g. 58.3% loss probability). │
└────────────────────────────────┴───────────────────────────────────────┘
```

### Critical Rules:
1. **Never label Empirical Negative-Net Frequency as a $p$-value.**  
   $P(\text{Net} \le 0) = 7.7\%$ is the simulated probability that an investor running 36 trades ends with zero or negative total profit. It is not an asymptotic hypothesis test $p$-value.
2. **Never claim that failure to reject $H_0$ proves the absence of an edge.**  
   A $p$-value of $0.1141$ means that the null hypothesis (zero edge) cannot be rejected at the 5% level. It does not prove the edge is zero; it indicates that the sample size ($N=36$) lacks sufficient statistical power to confirm an edge.
3. **Never claim statistical edge based on Profit Factor alone.**  
   A backtest Profit Factor of $1.602$ is an unweighted point estimate. Without evaluating its confidence interval and out-of-sample persistence, a point estimate is vulnerable to regime clustering and survivorship bias.

