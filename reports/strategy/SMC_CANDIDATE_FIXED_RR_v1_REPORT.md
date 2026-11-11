# GoldFlow — Strategy Candidate Experiment Report: SMC_CANDIDATE_FIXED_RR_v1
**Experiment ID:** `SMC_CANDIDATE_FIXED_RR_v1`  
**Execution Date:** 2026-11-11  
**Architecture Reference:** ADR-006 (Fixed 2R / 3R Target with Partial Exit)  
**Primary Framework:** Smart Money Concepts (SMC) v1  
**Target Instrument:** XAU/USD  
**Evaluation Mode:** Chronological Development Split (60% Development, 40% Locked Holdout)  

---

## 1. Executive Summary & Gate Decision

| Candidate ID | Timeframes Tested | Dev Split Ratio | Dev Performance | Validation Holdout | Gate Recommendation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SMC_CANDIDATE_FIXED_RR_v1** | H4, H1, M15, M5 | 60.0% (Development) | H4 PF 1.817, H1 PF 0.913, M15 PF 0.903, M5 PF 0.921 | **STRICTLY LOCKED** (40%) | **REJECT PROMOTION (GATE CLOSED)** |

### Gate Decision Rationale
Under the pre-registered criteria specified in `configs/candidate_specs/SMC_CANDIDATE_FIXED_RR_v1.json`:
1. **Promotion Threshold:** Requires Profit Factor $\ge 1.10$ on development period for H1 and/or M15, with max drawdown $\le 20\%$, and without degrading H4 baseline.
2. **Empirical Findings:**
   - **H1:** PF improved slightly from 0.892 to 0.913 (+0.021), but remained $< 1.0$.
   - **M15:** PF decreased from 1.018 to 0.903 (-0.115); fixed targets prematurely exited high-expectancy trend continuations that opposing liquidity pools captured.
   - **H4:** PF degraded from 2.478 to 1.817 (-0.661); capping gains at 2R and 3R truncates large institutional swing extensions on H4.
   - **M5:** Substantial reduction in cumulative losses (+$1,595.14 delta, reducing drawdown from \$5,955 to \$4,885 and increasing PF from 0.850 to 0.921), demonstrating that partial exits at 2R protect capital against rapid mean-reversion on low timeframes. However, M5 PF remains sub-unity ($0.921 < 1.00$).
3. **Formal Verdict:** Candidate fails the pre-registered promotion criteria ($\text{PF} < 1.10$). **The promotion gate remains CLOSED.** The validation holdout window (remaining 40%) was not unblinded, preserving research holdout integrity for future hypothesis testing.

---

## 2. Experimental Setup & Pre-Registered Specification

- **Baseline Architecture:** Order Block retest entry $\to$ Opposing Liquidity Pool target ($2.0\text{R}$ fallback if pool absent) $\to$ Invalidation beyond entry OB. Single position leg ($100\%$ lots).
- **Candidate Architecture (ADR-006):** Order Block retest entry $\to$ Split into two equal micro-lot orders:
  - **Leg A (50% lots):** Exits at fixed $2.0\text{R}$ initial risk multiple.
  - **Leg B (50% lots):** Exits at fixed $3.0\text{R}$ initial risk multiple.
  - Both legs share the origin OB invalidation stop loss.
  - Fractional micro-lot conservation: $\text{leg\_a} = \lfloor\text{lots}/2\rfloor$, $\text{leg\_b} = \text{lots} - \text{leg\_a}$.
- **Cost Assumptions:** $0.20/oz fallback spread, $0.05/oz slippage per side, \$0.00/lot commission (pure spread/slippage baseline).

---

## 3. Comparative Performance Matrix (60% Development Split)

| Timeframe | Data Bars (Dev) | Metric | Baseline (Opposing Pool) | Candidate (2R / 3R Split) | Delta | Impact Analysis |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **H4** | 3,000 | **Net Profit**<br>**Profit Factor**<br>**Win Rate**<br>**Max Drawdown**<br>**Closed Trades** | **+$566.48**<br>**2.478**<br>33.3%<br>$751.76 (7.2%)<br>6 | +$312.10<br>1.817<br>**42.9%**<br>**$213.04 (2.1%)**<br>14 | -$254.38<br>-0.661<br>+9.6%<br>-$538.72<br>+8 | Capped upside at 3R limits large H4 trend extensions, but drastically reduces drawdown (-71.6%). |
| **H1** | 6,000 | **Net Profit**<br>**Profit Factor**<br>**Win Rate**<br>**Max Drawdown**<br>**Closed Trades** | -$251.54<br>0.892<br>24.2%<br>$1,249.98 (11.7%)<br>33 | **-$184.79**<br>**0.913**<br>**28.3%**<br>**$1,161.43 (10.6%)**<br>60 | **+$66.75**<br>**+0.021**<br>+4.1%<br>-$88.55<br>+27 | Modest improvement in expectancy and win rate; partial exit locks profit before adverse reversal. |
| **M15** | 3,000 | **Net Profit**<br>**Profit Factor**<br>**Win Rate**<br>**Max Drawdown**<br>**Closed Trades** | **+$170.09**<br>**1.018**<br>21.1%<br>$1,048.52 (10.4%)<br>20 | -$49.94<br>0.903<br>**28.2%**<br>**$690.58 (6.8%)**<br>40 | -$220.03<br>-0.115<br>+7.1%<br>-$357.94<br>+20 | On M15 dev window, baseline caught occasional 4R+ pool runs; fixed 3R target reduced payoff. |
| **M5** | 59,999 | **Net Profit**<br>**Profit Factor**<br>**Win Rate**<br>**Max Drawdown**<br>**Closed Trades** | -$3,947.54<br>0.850<br>26.2%<br>$5,955.15 (55.2%)<br>485 | **-$2,352.40**<br>**0.921**<br>**27.4%**<br>**$4,885.01 (42.0%)**<br>933 | **+$1,595.14**<br>**+0.071**<br>+1.2%<br>-$1,070.14<br>+448 | Huge loss reduction on noisy lower timeframe; partial exit at 2R mitigates chop stopouts. |

---

## 4. Quantitative & Structural Insights

1. **Trade Splitting Mechanically Doubles Rule Exit Observations:**  
   Because each position splits into Leg A (2R) and Leg B (3R), closed trade count approximately doubles. When price reaches 2R but reverses before 3R, Leg A closes as a winner (+2R) while Leg B closes at the trailing stop (-1R or BE), generating a net positive outcome (+1R) where the baseline previously produced a full -1R loss.
2. **Timeframe Divergence:**  
   - Higher timeframes (H4) possess wider swings where opposing liquidity pools are often situated at 4R to 8R. Replacing dynamic liquidity targets with fixed 2R/3R targets creates an artificial performance ceiling on H4.
   - Lower timeframes (M5) suffer from structural noise where distant opposing liquidity pools are rarely achieved before intermediate structure shifts. On M5, 2R/3R partial exits significantly outperformed the baseline (+1,595 USD delta).
3. **Research Holdout Discipline:**  
   The remaining 40% of data across all timeframes was strictly preserved. Slicing was executed chronologically by timestamp index without looking ahead.

---

## 5. Artifact Provenance
- Raw metrics: `reports/strategy/candidate_fixed_rr_dev_results.json`
- Configuration spec: `configs/candidate_specs/SMC_CANDIDATE_FIXED_RR_v1.json`
- Runner: `scratch/run_candidate_dev_experiment.py`
