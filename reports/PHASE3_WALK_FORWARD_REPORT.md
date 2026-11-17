# Phase 3 Walk-Forward Validation Report
## 10-Fold Chronological Out-of-Sample Evaluation on 33,388 Bars

**Date:** 2026-11-17  
**Quantitative Researcher:** Systematic Trading Systems Architect  
**Strategy Under Evaluation:** `SMC_CONFLUENCE_V1` — Candidate `EXP_H_HTF_ATR`  
**Configuration:** HTF Bias (D1+H4) = ON, ATR Stops = ON, Session = OFF, News = OFF, Breakeven = OFF  
**Dataset:** `data/research/phase3/processed/XAUUSD_M15_extended.csv` (33,388 bars)  
**Machine-Readable Source:** `reports/PHASE3_WALK_FORWARD_VALIDATION.csv`  

---

## 1. Executive Summary & Research Gate Verdict

We conducted a 10-fold expanding-window chronological walk-forward validation across the entire 17-month XAU/USD history.

### The Research Target:
- **Requirement to Advance to Demo:** At least 7 out of 10 positive folds ($\ge 70\%$) with positive net expectancy across evaluation folds.
- **Observed Result:** **2 out of 10 folds positive (20.0%)**, aggregate out-of-sample P&L = **-$116.46**.

```
Research Gate Status: FAILED
==================================================
Positive Folds:        2 / 10 (20.0%)
Required Folds:        7 / 10 (70.0%)
Total OOS Trades:      36 trades
Total OOS Net P&L:     -$116.46
Average OOS PF:        0.963
VERDICT:               REMAIN IN RESEARCH. DO NOT PROCEED TO DEMO.
```

---

## 2. 10-Fold Walk-Forward Performance Table

Each fold evaluated an expanding in-sample training window followed by a strict out-of-sample evaluation slice of 2,000 bars (~1 month):

| Fold | In-Sample Period (Dates) | IS Bars | IS Trades | IS PF | Out-of-Sample Period (Dates) | OOS Bars | OOS Trades | OOS Win Rate | OOS Net P&L | OOS Profit Factor | OOS Drawdown | Fold Result |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **1** | 2025-05-13 → 2025-12-04 | 13,388 | 37 | 1.703 | 2025-12-04 → 2026-01-07 | 2,000 | 2 | 0.0% | -$87.97 | 0.000 | 0.88% | ❌ NEGATIVE |
| **2** | 2025-05-13 → 2026-01-07 | 15,388 | 39 | 1.532 | 2026-01-07 → 2026-02-06 | 2,000 | 4 | 75.0% | **+$201.71** | **6.212** | 0.50% | ✅ **POSITIVE** |
| **3** | 2025-05-13 → 2026-02-06 | 17,388 | 42 | 1.629 | 2026-02-06 → 2026-03-10 | 2,000 | 4 | 25.0% | -$27.49 | 0.748 | 0.82% | ❌ NEGATIVE |
| **4** | 2025-05-13 → 2026-03-10 | 19,388 | 47 | 1.469 | 2026-03-10 → 2026-04-12 | 2,000 | 3 | 0.0% | -$120.40 | 0.000 | 1.20% | ❌ NEGATIVE |
| **5** | 2025-05-13 → 2026-04-12 | 21,388 | 53 | 1.482 | 2026-04-12 → 2026-05-13 | 2,000 | 5 | 40.0% | -$45.23 | 0.672 | 1.15% | ❌ NEGATIVE |
| **6** | 2025-05-13 → 2026-05-13 | 23,388 | 59 | 1.378 | 2026-05-13 → 2026-06-15 | 2,000 | 3 | 0.0% | -$128.30 | 0.000 | 1.28% | ❌ NEGATIVE |
| **7** | 2025-05-13 → 2026-06-15 | 25,388 | 67 | 1.348 | 2026-06-15 → 2026-07-16 | 2,000 | 0 | 0.0% | $0.00 | 0.000 | 0.00% | ➖ NEUTRAL |
| **8** | 2025-05-13 → 2026-07-16 | 27,388 | 71 | 1.366 | 2026-07-16 → 2026-08-18 | 2,000 | 6 | 33.3% | -$28.36 | 0.852 | 1.05% | ❌ NEGATIVE |
| **9** | 2025-05-13 → 2026-08-18 | 29,388 | 77 | 1.257 | 2026-08-18 → 2026-09-17 | 2,000 | 1 | 0.0% | -$34.57 | 0.000 | 0.35% | ❌ NEGATIVE |
| **10**| 2025-05-13 → 2026-09-17 | 31,388 | 78 | 1.230 | 2026-09-18 → 2026-10-20 | 2,000 | 8 | 50.0% | **+$154.15** | **1.912** | 1.35% | ✅ **POSITIVE** |

---

## 3. Deep Analysis of Walk-Forward Failure

### 3.1 Unmasking the Phase 2 Illusion
In Phase 2, the only out-of-sample window evaluated was **Fold 10** (September 18 to October 20, 2026). In that single window, EXP_H generated 8 trades, a 50% win rate, and a profit factor of **1.912** (+154.15).

When evaluated across the entire 17-month history, we now see that **Fold 10 was an unrepresentative positive outlier**. In 7 of the other 9 folds, the strategy generated net losses.

### 3.2 In-Sample vs Out-of-Sample Divergence
A striking pattern is visible:
- **In-Sample Performance:** Consistently positive across all 10 expanding windows (IS PF = 1.230 to 1.703, Net = +$478 to +$666).
- **Out-of-Sample Performance:** Fails in 80% of evaluation slices (PF = 0.000 to 0.852).

This severe degradation between In-Sample and Out-of-Sample performance is the textbook signature of **structural regime dependency** and **over-filtering**:
1. When the market trends strongly (e.g., January 2026 and October 2026), HTF bias alignment generates spectacular multi-R winners.
2. In transitional, choppy, or rotating regimes (e.g., March to June 2026), higher-timeframe signals lag the turn, causing entries right into market reversals.

---

## 4. Multi-Dimensional Breakdown of Out-of-Sample Trades

| Dimension | Category | OOS Trades | Win Rate | Net P&L | Profit Factor |
|:---|:---|:---:|:---:|:---:|:---:|
| **Trade Direction** | Long (Bullish) | 18 | 38.9% | +$42.10 | 1.092 |
| | Short (Bearish) | 18 | 27.8% | -$158.56 | 0.621 |
| **Session** | London (07-13 UTC) | 14 | 42.9% | +$182.40 | 1.642 |
| | NY (13-21 UTC) | 12 | 33.3% | -$84.10 | 0.781 |
| | Asian / Offhours | 10 | 20.0% | -$214.76 | 0.380 |
| **Regime** | Trending (ADX > 25) | 11 | 45.5% | +$141.20 | 1.582 |
| | Ranging (ADX $\le$ 25)| 25 | 28.0% | -$257.66 | 0.614 |

### Critical Takeaways:
1. **Short trades were a primary drag:** Gold was in a macro bull market across 2025–2026; short SMC setups had a win rate of only 27.8% and a profit factor of 0.621.
2. **Ranging markets destroyed performance:** In ranging regimes (ADX $\le$ 25), the strategy lost -$257.66 with a 28% win rate.
3. **Asian/Off-hours trading was deeply negative:** Out-of-sample Asian session trading had a 20.0% win rate and PF = 0.380.

---

## 5. Formal Recommendation

The strategy **fails Gate 3C**. It is not statistically robust.
Do NOT deploy capital. Do NOT enable MT5 demo trading.
The platform must remain in quantitative research.
