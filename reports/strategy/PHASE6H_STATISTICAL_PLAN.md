# PHASE 6H — Statistical Research and Evaluation Plan
## Sample Size Justification, Tail Risk Accounting, and Promotion Thresholds for Candidate C2

**Repository Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Candidate Name:** `SMC_v2_target_rationalized` (C2)  
**Date:** 2026-10-30 | **Status:** METHODOLOGY SPECIFIED  

---

## 1. Mathematical Sample Size Justification

In quantitative research, arbitrary rules of thumb (e.g., "require 200 trades") are insufficient. Sample size requirements must be derived from the variance of the underlying payoff distribution, expected edge magnitude, and test power.

### 1.1 Payoff Distribution Modeling

For candidate C2 (Fixed 2.0R target), trade outcomes in normalized R-multiples are approximately bimodal:
- **Winning Trade:** Realized $R \approx +1.8\text{R}$ to $+2.0\text{R}$ (after friction).
- **Losing Trade:** Realized $R \approx -1.0\text{R}$ (stop-loss with modeled slippage).

Let $p$ denote the true win rate. The expected net R-multiple per trade is:
$$\mu_R = p \cdot R_{\text{win}} - (1 - p) \cdot |R_{\text{loss}}|$$
The variance of the outcome per trade is:
$$\sigma_R^2 = p \cdot (R_{\text{win}} - \mu_R)^2 + (1 - p) \cdot (-|R_{\text{loss}}| - \mu_R)^2$$

### 1.2 Required Sample Size for Statistical Significance

To reject the null hypothesis of zero edge ($H_0: \mu_R \le 0$) at significance level $\alpha = 0.05$ (one-tailed $z_\alpha = 1.645$) with statistical power $1 - \beta = 0.80$ ($z_\beta = 0.842$), the required number of independent closed trades $N$ is:
$$N \ge \left( \frac{(z_\alpha + z_\beta) \cdot \sigma_R}{\mu_R} \right)^2$$

Evaluating this formula across plausible SMC edge scenarios:

| Win Rate $p$ | Win Payoff $R_{\text{win}}$ | Expected $R$ ($\mu_R$) | Std Dev ($\sigma_R$) | Implied Profit Factor | Required Trades ($N$) |
|---|---|---|---|---|---|
| **34.0%** | +1.95R | +0.003R | 1.41R | 1.005 (Breakeven) | $> 1,000,000$ |
| **35.0%** | +1.95R | +0.033R | 1.43R | 1.050 (Thin edge) | **~11,600 trades** |
| **36.0%** | +1.95R | +0.062R | 1.44R | 1.096 (Moderate edge) | **~3,300 trades** |
| **38.0%** | +1.95R | +0.121R | 1.46R | 1.195 (Solid edge) | **~890 trades** |
| **40.0%** | +1.95R | +0.180R | 1.47R | 1.300 (Strong edge) | **~410 trades** |

### 1.3 Methodological Conclusion on Sample Size

- **The Phase 6F Development Sample ($n=59$ trades):** With 59 trades, standard error $\text{SE}(\bar{R}) \approx \frac{1.44}{\sqrt{59}} \approx \mathbf{0.187\text{R}}$. The observed mean R (+0.048R) is well within $0.26$ standard errors of zero. It has **statistical power $< 12\%$**.
- **The Phase 6G Validation Sample ($n=6$ trades):** With 6 trades, standard error $\text{SE}(\bar{R}) \approx \frac{1.44}{\sqrt{6}} \approx \mathbf{0.588\text{R}}$. It is completely uninformative.
- **Minimum Defensible Milestone Threshold:** To establish statistical significance against $H_0$ with $\ge 80\%$ power, C2 requires an independent evaluation sample of **at least 400 to 900 closed trades** under consistent execution costs.

---

## 2. Tail Concentration Audit of Candidate C2

An audit of the 59 closed development trades of C2 (`trades_M15_SMC_v2_target_rationalized.csv`) reveals that C2 suffers from a similar concentration vulnerability to C1:

- **Total Strategy Net P&L:** **+$282.81** (across 21 wins, 38 losses).
- **Largest Single Win:** **+$201.36** (accounts for **71.2%** of net profit).
- **Top 3 Winning Trades:** Sum to **+$595.65** (account for **210.6%** of net profit).
- **Net P&L Without Top 3 Trades:** **-$312.84**.

**Implication:**  
Like C1, candidate C2's profitability on the development set is not a uniform edge; it is heavily dependent on a handful of oversized winners. Any valid statistical evaluation must verify whether this tail asymmetry is a persistent feature of SMC expansion waves or a sample artifact.

---

## 3. Clustered Dependence & Market Regime Coverage

In financial time series, trades are not independent and identically distributed (i.i.d.). They exhibit:
1. **Volatility Clustering:** Consecutive trades occur in the same volatility regime.
2. **Structural Autocorrelation:** Multiple setups trigger along the same macro trend leg.

### Mandatory Multi-Regime Requirement

A valid evaluation dataset for C2 cannot be confined to a single 2-month window. The evaluation data must span at least **three distinct macroeconomic regimes**:
1. **Trending Bull Regime:** Gold in sustained directional expansion.
2. **Trending Bear Regime:** Gold in extended multi-week liquidation.
3. **High-Volatility Range / Compression:** Choppy, mean-reverting chop where CHoCH signals produce false breakouts.

---

## 4. Formal Research Promotion Gate Criteria for Phase 6I

For Candidate C2 to advance from **EXPLORATORY CANDIDATE** to **RESEARCH-VALIDATED CANDIDATE**, it must satisfy all of the following non-negotiable criteria in an independent evaluation:

```
┌──────────────────────────────────────┬────────────────────────────────────────────────────────┐
│ Criterion                            │ Required Threshold                                     │
├──────────────────────────────────────┼────────────────────────────────────────────────────────┤
│ Sample Size                          │ N >= 400 closed trades on untouched data               │
│ Net Profit Factor                    │ PF >= 1.15 (under 1.0x modeled costs)                  │
│ Directional Robustness               │ Net P&L > 0 on both Long and Short sub-portfolios      │
│ Regime Stability                     │ Net P&L > 0 in at least 70% of rolling 90-day windows  │
│ Outlier Resilience                   │ Net P&L remains positive after removing top 3% of wins │
│ Cost Sensitivity (Fixed Lots)        │ PF >= 1.05 under 2.0x spread and slippage              │
│ Maximum Drawdown                     │ Max Realized Drawdown <= 25.0% of peak equity          │
└──────────────────────────────────────┴────────────────────────────────────────────────────────┘
```

