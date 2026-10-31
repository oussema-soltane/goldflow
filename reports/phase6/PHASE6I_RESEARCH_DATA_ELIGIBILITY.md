# GOLDFLOW — PHASE 6I: STAGE E
## Research Data Eligibility Classification & Statistical Power Harmonization

**Date:** 2026-10-30  
**Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Object Format:** `sha1`  
**Author:** Quantitative Architecture & Statistical Validation Team  
**Scope:** Dataset contamination audit, untouched data criteria, and statistical power reconciliation for candidate C2.

---

## 1. Executive Summary

A critical finding of Phase 6H was that all existing M15 bar data in the repository has been repeatedly examined during candidate generation, diagnostic loss decomposition, and validation trials. Consequently, **no currently existing M15 data is eligible for independent statistical hypothesis testing**.

This report establishes:
1. An exhaustive classification and quarantine status for every dataset in the GoldFlow repository.
2. The rigorous mathematical criteria that newly acquired historical data must meet to be certified as "Untouched".
3. A formal mathematical reconciliation of the sample size targets: bridging the gap between the **Interim Directional Milestone ($N \ge 400\text{–}900$ trades)** and the **Theoretical Statistical Power Requirement ($N \approx 3,300$ trades)**.

---

## 2. Comprehensive Dataset Classification Matrix

To prevent data snooping, p-hacking, and survivorship bias, all datasets currently present within `data/` are classified according to GoldFlow research governance:

| Dataset Path | Timeframe / Scope | Record Count | Research Status | Rationale & Constraint |
|:---|:---:|:---:|:---:|:---|
| `data/processed/XAUUSD_M5_clean.csv` | M5 (2026) | 99,148 bars | **EXAMINED / CONTAMINATED** | Used extensively in Phase 6F for initial candidate mining, loss decomposition, and cost drag analysis. Ineligible for out-of-sample testing. |
| `data/processed/XAUUSD_M15_clean.csv` | M15 (2026) | 33,049 bars | **EXAMINED / CONTAMINATED** | Primary exploration set where C0, C1, and C2 development trades ($N=59$) were evaluated. Ineligible for validation. |
| `data/processed/XAUUSD_M15_validation_window.csv` | M15 (2026-10) | 4,000 bars | **EXAMINED / CONTAMINATED** | Used in Phase 6G to evaluate C1 and C2 ($N=6$). Result was scrutinized and used to reject C1 and advance C2. Contaminated for further C2 testing. |
| `data/processed/XAUUSD_H1_clean.csv` | H1 (2025–2026) | 9,931 bars | **EXAMINED / BENCHMARK** | Used for MTF market structure context and Stage B calibration reference. Eligible for reference quote verification only. |
| `data/processed/XAUUSD_H4_clean.csv` | H4 (2025–2026) | 2,482 bars | **EXAMINED / BENCHMARK** | Higher timeframe trend context. Eligible for MTF context only. |
| `data/quarantine/legacy_m15_quarantine/*` | M15 legacy | 9,923 bars | **QUARANTINED** | Archived due to POSIX timestamp drift and missing tick volume anomalies. |
| `data/quarantine/m15_posix_utc_quarantine_*`| M15 legacy | 9,923 bars | **QUARANTINED** | Archived duplicate. Ineligible for any research. |
| `data/synthetic/*` | Synthetic fixtures | N/A | **SYNTHETIC_FIXTURE_ONLY**| Explicit test fixtures for unit tests. Ineligible for real market inference. |

---

## 3. Definition and Certification Criteria for "Untouched" Data

Newly acquired historical data from the Phase 6J historical acquisition campaign can only be certified as **ELIGIBLE UNTOUCHED DATA** if it satisfies the following four conditions:

1. **Temporal Disjointness:** The data must cover time periods strictly outside the examined MT5 export window (e.g., prior historical years 2024–2025, or newly acquired contiguous months).
2. **Zero Prior Optimization Exposure:** The data must never have been visualized in TradingView, inspected via Pandas, plotted on charts, or processed by any parameter optimization sweep.
3. **Verified Scaling Provenance:** Ingested using the promoted `VERIFIED` Dukascopy specification with cryptographic SHA-256 partition manifests.
4. **Physical Vault Segregation:** Stored in segregated partition directories (`data/vault/dukascopy/partitions/`) with write-protection enabled.

---

## 4. Statistical Sample Size Harmonization

In Phase 6G and 6H, two distinct sample size figures were discussed. This section provides the rigorous statistical derivation that harmonizes them.

### 4.1 The Theoretical Asymptotic Power Requirement ($N \approx 3,300$)
Consider a quantitative strategy whose true underlying edge per trade $R$ has a small positive mean $\mu_R = +0.062\text{R}$ (consistent with a realistic long-term post-cost edge in retail gold trading, corresponding to $\text{Profit Factor} \approx 1.08\text{–}1.10$ with standard deviation $\sigma_R \approx 1.0\text{R}$).

We wish to test the null hypothesis that the strategy has zero or negative edge:
$$H_0: \mu_R \le 0 \quad \text{vs.} \quad H_1: \mu_R > 0$$

Using a two-sided test with significance level $\alpha = 0.05$ ($Z_{\alpha/2} = 1.960$) and desired statistical power $1 - \beta = 0.95$ ($Z_\beta = 1.645$):

$$N = \left( \frac{Z_{\alpha/2} + Z_\beta}{\delta} \right)^2$$

Where the effect size (standardized mean edge) is:
$$\delta = \frac{\mu_R}{\sigma_R} = \frac{0.062}{1.0} = 0.062$$

Substituting the parameters:
$$N = \left( \frac{1.960 + 1.645}{0.062} \right)^2 = \left( \frac{3.605}{0.062} \right)^2 = (58.145)^2 \approx \mathbf{3,380 \text{ trades}}$$

**Conclusion on Theoretical Power:**  
To **definitively prove** that a subtle edge ($\mu_R = 0.062\text{R}$) is statistically indistinguishable from zero with $95\%$ certainty against false discovery, an asymptotic sample of approximately **3,300 to 3,400 completed trades** is mathematically required.

### 4.2 The Interim Directional Milestone ($N \ge 400\text{–}900$)
In practical quantitative finance, waiting for $3,300$ trades on a 15-minute timeframe (which generates $\approx 25\text{–}35$ trades per month, requiring nearly 10 years of data) would stall all research progress.

Instead, quantitative validation uses an **interim directional gate**:
- **Objective:** Reject severe negative expectancy or random-walk noise ($H_0: \text{PF} \le 0.90$ or $\mu_R \le -0.10\text{R}$) with $90\%$ confidence ($Z = 1.282$).
- **Minimum Threshold:** At $N = 400$, the standard error of the mean R is:
  $$\text{SE}(\bar{R}) = \frac{\sigma_R}{\sqrt{N}} = \frac{1.0}{\sqrt{400}} = 0.050\text{R}$$
  A 95% confidence interval has half-width $1.96 \times 0.050 = \pm 0.098\text{R}$.
- At $N = 900$:
  $$\text{SE}(\bar{R}) = \frac{1.0}{\sqrt{900}} = 0.033\text{R}$$
  A 95% confidence interval has half-width $1.96 \times 0.033 = \pm 0.065\text{R}$.

### 4.3 Synthesis and Harmonization Table

| Validation Tier | Target Sample Size ($N$) | Required Data Window (M15) | Statistical Objective | Decision Action |
|:---|:---:|:---:|:---|:---|
| **Exploratory (Current)** | $N = 59$ (Dev), $N = 6$ (Val) | 1–2 months | Detect gross anomalies, verify logic | **Candidate retained as exploratory only (Phase 6H)** |
| **Interim Validation Gate** | **$N = 400\text{–}900$ trades** | **12–24 months** | Narrow $\text{SE}(\bar{R})$ to $\le 0.05\text{R}$; reject $H_0: \text{PF} \le 1.0$ at $90\%$ confidence | **Authorizes promotion from Exploratory to Paper/Forward Incubator** |
| **Asymptotic Gate** | **$N \approx 3,300$ trades** | **5–8 years (or Multi-Pair)** | Reject $H_0: \mu_R \le 0$ at $95\%$ power for subtle edge ($\mu_R = 0.062\text{R}$) | **Authorizes institutional capital allocation** |

---

## 5. Conclusion

The dual sample-size targets are fully reconciled:
- **$N \ge 400\text{–}900$ trades** is the operational requirement for **Phase 6J validation** achievable via the 12–24 month Dukascopy acquisition plan.
- **$N \approx 3,300$ trades** is the long-term theoretical gold standard for statistical edge certainty.

Acquiring 24 months of genuine historical M15 data will produce approximately **500 to 800 trades**, perfectly satisfying the interim directional validation requirement.

