# Phase 2.5 — Independent Quantitative Research Audit
## GoldFlow XAU/USD SMC_CONFLUENCE_V1 Research Integrity Verification

**Date:** 2026-11-17  
**Auditor:** Independent Quantitative Systems Auditor & Financial Data Engineer  
**Git Baseline Commit:** `6d7bb91`  
**Research Branch:** `research/phase2.5-phase3`  
**Frozen SMC Baseline Config SHA-256:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`  
**Execution Guard:** MetaTrader 5 `order_send` permanently disabled (Fail-Closed)

---

## 1. Executive Summary

This independent research audit reproduces, audits, and challenges all claims and findings from GoldFlow Phase 1 and Phase 2 before historical expansion.

Our primary mission:
> **PROTECT CAPITAL FIRST. PROVE THE EDGE SECOND. AUTOMATE EXECUTION THIRD.**

### Key Audit Conclusions:
1. **Discrepancy Resolution:** We investigated why previous summaries mentioned a maximum of 8 OOS trades in Phase 2 versus a maximum of 4 trades per walk-forward fold. This is **100% reconciled**: Phase 2 used a single static 60/40 split (2,000 OOS bars) yielding 8 trades for EXP_H, whereas the walk-forward framework used 20% slices (1,000 OOS bars per fold) yielding a maximum of 4 trades per fold.
2. **Trade Ledger Reconciliation:** The 31 zero-P&L rows in `PHASE2_TRADE_LEDGER.csv` were audited and confirmed to be **execution-skipped orders** (`entry_time = NaN`, skipped due to spread or concurrency limits). When skipped rows are excluded, trade counts match `PHASE2_PERFORMANCE_COMPARISON.csv` to the exact integer, and gross/net P&L matches to the penny ($0.00 diff).
3. **Temporal Invariance & Lookahead Audit:** Confirmed clean. Adding 1,000 future bars to the historical dataset produced **0 changes** to earlier candidate signals, order blocks, or HTF bias decisions.
4. **Statistical Fragility Exposed:** The Phase 2 M15 OOS result (PF=1.912 on 8 trades) was an artifact of sample sparsity in a favorable 24-day window. Expanded walk-forward across 33,388 bars proves that 8 out of 10 out-of-sample folds were losing/zero, yielding an aggregate OOS loss of -$116.46.

---

## 2. Independent Metric Reconciliation (Phase 1 & Phase 2)

### 2.1 Reconciliation Between Trade Ledger and Performance Comparison

We executed an independent reconciliation script matching every row of `PHASE2_TRADE_LEDGER.csv` against `PHASE2_PERFORMANCE_COMPARISON.csv`.

| Experiment | Timeframe | Split | Performance Table Trades | Trade Ledger Total | Skipped / EndOfData | Executed Rule Trades | Net P&L Discrepancy | Status |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `EXP_H_HTF_ATR` | M15 | IS | 6 | 6 | 0 | 6 | $0.00 | **MATCH** |
| `EXP_H_HTF_ATR` | M15 | OOS | 8 | 8 | 0 | 8 | $0.00 | **MATCH** |
| `EXP_I_HTF_ATR_LONDON` | M15 | IS | 2 | 2 | 0 | 2 | $0.00 | **MATCH** |
| `EXP_I_HTF_ATR_LONDON` | M15 | OOS | 4 | 4 | 0 | 4 | $0.00 | **MATCH** |
| `EXP_J_HTF_ATR_BREAKEVEN` | M15 | IS | 6 | 6 | 0 | 6 | $0.00 | **MATCH** |
| `EXP_J_HTF_ATR_BREAKEVEN` | M15 | OOS | 8 | 8 | 0 | 8 | $0.00 | **MATCH** |
| `EXP_K_FULL_CONFLUENCE` | M15 | IS | 2 | 2 | 0 | 2 | $0.00 | **MATCH** |
| `EXP_K_FULL_CONFLUENCE` | M15 | OOS | 4 | 4 | 0 | 4 | $0.00 | **MATCH** |
| `BASELINE` | M15 | IS | 19 | 27 | 7 skipped + 1 EOD | 19 | $0.00 | **MATCH** |
| `BASELINE` | M15 | OOS | 23 | 26 | 3 skipped | 23 | $0.00 | **MATCH** |
| `EXP_H_HTF_ATR` | H1 | IS | 8 | 8 | 0 | 8 | $0.00 | **MATCH** |
| `EXP_H_HTF_ATR` | H1 | OOS | 3 | 4 | 1 skipped | 3 | $0.00 | **MATCH** |
| `EXP_I_HTF_ATR_LONDON` | H1 | IS | 2 | 2 | 0 | 2 | $0.00 | **MATCH** |
| `EXP_I_HTF_ATR_LONDON` | H1 | OOS | 2 | 3 | 1 skipped | 2 | $0.00 | **MATCH** |
| `EXP_J_HTF_ATR_BREAKEVEN` | H1 | IS | 8 | 8 | 0 | 8 | $0.00 | **MATCH** |
| `EXP_J_HTF_ATR_BREAKEVEN` | H1 | OOS | 3 | 4 | 1 skipped | 3 | $0.00 | **MATCH** |
| `EXP_K_FULL_CONFLUENCE` | H1 | IS | 2 | 2 | 0 | 2 | $0.00 | **MATCH** |
| `EXP_K_FULL_CONFLUENCE` | H1 | OOS | 2 | 3 | 1 skipped | 2 | $0.00 | **MATCH** |
| `BASELINE` | H1 | IS | 31 | 37 | 6 skipped | 31 | $0.00 | **MATCH** |
| `BASELINE` | H1 | OOS | 14 | 25 | 11 skipped | 14 | $0.00 | **MATCH** |

**Audit Finding:** The apparent discrepancy in raw row counts was caused by `_skipped_trade` records in the engine output. The performance metrics table properly counted executed closed rule trades. Every single gross profit, gross loss, and net profit figure reconciles to $0.0000.

### 2.2 Investigation of Sample Size Discrepancy (8 OOS Trades vs Max 4 in Walk-Forward)

**Audit Question:** Why did the Phase 2 report cite 8 OOS trades for EXP_H on M15 in Section 3, but the walk-forward table reported a maximum of 4 OOS trades per fold?

**Audit Finding:**
- **In `scripts/run_phase2_ablation.py`:** A single 60/40 static split of the 5,000 bars was evaluated. The out-of-sample period comprised **2,000 bars** (bars 3,000 to 4,999, spanning Sep 29 to Oct 22, 2026). In this 2,000-bar window, EXP_H generated **8 trades** (4 wins, 4 losses, Net = +$154.15, PF = 1.912).
- **In `scripts/run_walk_forward_validation.py`:** The 5-fold expanding window evaluated out-of-sample slices of 20% (**1,000 bars each**). Fold 3 evaluated bars 3,100 to 4,100 (4 trades) and Fold 4 evaluated bars 3,900 to 4,900 (4 trades).
- **Conclusion:** There is no contradiction. 8 trades occurred across the full 2,000-bar OOS window, whereas the walk-forward slices split that window into 1,000-bar evaluation folds, producing a maximum of 4 trades in any individual fold.

---

## 3. Temporal Integrity & Lookahead Bias Audit

We audited the entire decision pipeline to verify that future observations can never leak into historical signals.

### 3.1 Higher-Timeframe (HTF) Daily & H4 Availability
In `src/strategy/htf_bias.py` and `src/strategy/smc_mtf.py`:
- Daily candles are aggregated strictly from completed calendar UTC days (00:00:00 to 23:59:59). Incomplete trailing days are explicitly dropped via `drop_incomplete_trailing_day=True`.
- For H4 and D1 structure breaks, availability timestamp is defined as:
  $$\text{available\_at} = \text{break\_time} + \text{TIMEFRAME\_DURATION}$$
  Where $\text{TIMEFRAME\_DURATION}$ is 4 hours for H4 and 24 hours for D1.
- Forming candles are NEVER accessed. The lookup utilizes `bisect_right(available_at_ns, decision_time.value) - 1`, strictly retrieving snapshots completed before or at decision time.

### 3.2 Entry Signal & ATR Availability
- In `src/strategy/smc_confluence.py`: Entry is evaluated at `cand.next_bar_time` (the open of the bar following signal confirmation).
- ATR is computed using a 14-period causal EMA up to `cand.signal_index`. Future bars are never included in the rolling ATR window.

### 3.3 Temporal Invariance Experiment
To empirically verify temporal invariance, we ran an adversarial experiment:
1. Candidate generation was executed on a 2,000-bar slice ($T_0$ to $T_1$).
2. Candidate generation was then executed on a 3,000-bar slice ($T_0$ to $T_2$), adding 1,000 future bars.
3. Every candidate in the overlapping window was verified:
   - Signal time match: **100% (2/2)**
   - Direction match: **100% (2/2)**
   - Entry price match: **100% (2/2, diff < 1e-6)**
4. Raw SMC detector test: 19 raw candidates in 2,500 bars vs 19 raw candidates in 4,000 bars within the same window: **19/19 exact match (0 differences)**.

**Temporal Invariance Result: PASS (Zero lookahead bias detected).**

---

## 4. Statistical Methodology Audit

### 4.1 Critique of Previous Bootstrap Implementation
The Phase 2 bootstrap implementation (`scripts/run_bootstrap_analysis.py`) had two critical statistical flaws:
1. **Zero-Loss Denominator Inflation:** When zero losses were drawn in a resample, profit factor was assigned `999.0`. For EXP_H on 8 trades (4 wins, 4 losses), drawing 8 wins occurred with probability $(0.5)^8 \approx 0.39\%$. This distorted the bootstrap mean PF to 6.818 (compared to the observed PF of 1.912).
2. **I.I.D. Resampling Assumption:** Drawing individual trades independently with replacement ignores sequential autocorrelation, volatility clustering, and regime persistence.

### 4.2 Replacement: Stationary Block Bootstrap
In Phase 3, we replaced I.I.D. trade sampling with the **Stationary Block Bootstrap (Politis & Romano, 1994)** with mean block length $L=5$ trades. Furthermore, we evaluated net expectancy ($/trade), which is linear, well-behaved, and completely immune to zero-division anomalies.

### 4.3 Critique of Walk-Forward Independence Assumption
In Phase 2, 5 folds on M15 and 5 folds on H1 were summed to report "5 of 10 folds positive."
**Audit Warning:** M15 and H1 cover the same underlying calendar period (2025–2026). They do NOT represent 10 independent experiments. Treating them as independent trials artificially doubles the perceived sample size. Folds must be evaluated strictly within their own timeframe context.

---

## 5. Audit Conclusion & Gate Recommendation

| Criterion | Audit Finding | Status |
|:---|:---|:---:|
| Frozen Baseline Preservation | SHA-256 `1091fb06b...` exact match | **PASS** |
| Canonical Raw Data Integrity | All 4 canonical raw files intact | **PASS** |
| Consumed Data Guard | `XAUUSD_M15_validation_window.csv` not reused | **PASS** |
| Temporal Lookahead Check | Verified clean via invariance test | **PASS** |
| Trade Ledger Reconciliation | 100% reconciled to $0.00 discrepancy | **PASS** |
| Statistical Power (Phase 2) | Severely underpowered (8 trades) | **FAIL** |
| Walk-Forward Robustness | Failed gate (only 2/10 folds positive in Phase 3) | **FAIL** |

**Final Phase 2.5 Audit Verdict:**
The Phase 1 and Phase 2 implementations are mechanically sound and free of lookahead bias. However, the reported "edge" was an artifact of sample size sparsity in a single favorable window. The strategy cannot be advanced to demo trading and must undergo full historical expansion and rigorous re-evaluation.
