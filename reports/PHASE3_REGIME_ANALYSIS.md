# Phase 3 Regime, Session & Directional Robustness Report
## Multi-Dimensional Performance Decomposition for XAU/USD SMC_CONFLUENCE_V1

**Date:** 2026-11-17  
**Quantitative Specialist:** Regime Modeling & Market Microstructure Engineering  
**Dataset:** `XAUUSD_M15_extended.csv` (33,388 bars, May 2025 – October 2026)  
**Strategy Under Study:** `SMC_CONFLUENCE_V1` — Candidate `EXP_H_HTF_ATR` (88 trades)  
**Machine-Readable Source:** `reports/PHASE3_REGIME_ANALYSIS.csv`  

---

## 1. Executive Summary

This report performs a granular decomposition of trading performance across market regimes, volatility environments, intraday liquidity sessions, and directional bias.

### Key Robustness Findings:
1. **Regime Dependency:** The strategy generated **+$305.62 (PF=1.460)** during Trending regimes (ADX > 25), but degraded to barely breakeven **+$115.96 (PF=1.067)** during Ranging regimes (ADX $\le$ 25).
2. **Session Concentration (The True Edge):** The strategy generated **+$957.95 (PF=1.998)** during the London and New York Overlap sessions (07:00–17:00 UTC), but suffered severe drag of **-$429.16 (PF=0.630)** during Asian and Off-hours trading.
3. **Volatility Invariance:** ATR stop expansion successfully normalized volatility: Low Volatility (PF=1.208, +$271.19) and High Volatility (PF=1.139, +$150.39) showed balanced performance.
4. **Session Filter Autopsy:** The previous failure of the standalone session filter was caused by applying it without HTF bias (which merely concentrated losing counter-trend trades). When coupled with HTF bias, trading London/NY is the primary source of alpha.

---

## 2. Market Regime Robustness (ADX > 25 Trending vs $\le 25$ Ranging)

| Regime | Definition | Trades | Win Rate | Gross Profit | Gross Loss | Net P&L | Profit Factor | Expectancy ($/trade) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **TRENDING** | ADX(14) > 25.0 | 25 | **40.0%** | $969.62 | $664.00 | **+$305.62** | **1.460** | **+$12.22** |
| **RANGING** | ADX(14) $\le$ 25.0 | 63 | 36.5% | $1,840.97 | $1,725.01 | +$115.96 | 1.067 | +$1.84 |

**Insight:** In trending regimes, order blocks act as reliable continuation springboards with institutional participation. In ranging regimes, price chops back and forth through order blocks, triggering stop-losses before any sustainable expansion.

---

## 3. Volatility Regime Robustness (High Vol vs Low Vol)

Volatility regimes were defined relative to the median 14-period ATR ($7.84 on M15):

| Volatility Regime | Definition | Trades | Win Rate | Gross Profit | Gross Loss | Net P&L | Profit Factor | Expectancy ($/trade) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **LOW VOLATILITY** | ATR(14) $\le$ $7.84 | 46 | 37.0% | $1,574.60 | $1,303.41 | **+$271.19** | **1.208** | **+$5.90** |
| **HIGH VOLATILITY** | ATR(14) > $7.84 | 42 | 38.1% | $1,235.99 | $1,085.60 | **+$150.39** | **1.139** | **+$3.58** |

**Insight:** Performance is remarkably robust across volatility environments. The ATR stop-loss mechanism dynamically expands stops during high volatility and contracts them during quiet periods, successfully shielding the strategy from volatility shocks.

---

## 4. Intraday Session Robustness

| Session Name | UTC Operating Window | Trades | Win Rate | Gross Profit | Gross Loss | Net P&L | Profit Factor | Expectancy |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **LONDON** | 07:00 – 13:00 UTC | 24 | **50.0%** | $1,147.26 | $533.90 | **+$613.36** | **2.148** | **+$25.56** |
| **NY OVERLAP** | 13:00 – 17:00 UTC | 19 | **42.1%** | $764.20 | $419.61 | **+$344.59** | **1.822** | **+$18.14** |
| **LATE NY** | 17:00 – 21:00 UTC | 8 | 25.0% | $166.75 | $273.96 | -$107.21 | 0.609 | -$13.40 |
| **ASIAN / OFFHOURS** | 21:00 – 07:00 UTC | 37 | 29.7% | $732.38 | $1,161.54 | **-$429.16** | **0.630** | **-$11.60** |

```
Cumulative Session P&L Contribution:
==================================================
London + NY Overlap (07:00 - 17:00 UTC):  +$957.95 (PF = 1.998)
Late NY + Asian (17:00 - 07:00 UTC):     -$536.37 (PF = 0.626)
--------------------------------------------------
Total Candidate Net P&L:                  +$421.59 (PF = 1.176)
```

**Critical Discovery:**
Over 100% of the strategy's total net profits were generated during the London and NY Overlap windows (+$957.95). Trading during the Asian session and post-NY dead zone gave back -$536.37 of profit.

---

## 5. Forensic Autopsy: Why Did the Session Filter Harm the Baseline?

In Phase 1, applying the session filter to the raw baseline decreased P&L from -$298 to -$338. Why?

| Baseline Trades by Session | Trades | Win Rate | Net P&L | Profit Factor | Expectancy |
|:---|:---:|:---:|:---:|:---:|:---:|
| London (07:00 - 13:00 UTC) | 58 | 25.9% | -$237.62 | 0.874 | -$4.10 |
| NY Overlap (13:00 - 17:00 UTC) | 57 | 21.1% | -$557.11 | 0.709 | -$9.77 |
| Late NY (17:00 - 21:00 UTC) | 32 | 43.8% | +$850.93 | 2.154 | +$26.59 |
| Asian / Offhours | 116 | 31.9% | -$355.01 | 0.898 | -$3.06 |

### Autopsy Conclusion:
1. **Raw SMC without HTF Bias is Counter-Trend in London/NY:** During London and NY, institutional liquidity drives large directional trends. Raw SMC detects internal liquidity sweeps and order blocks that frequently attempt to fade strong institutional momentum. Thus, raw SMC in London/NY lost -$794.73!
2. **HTF Bias Inverts the Equation:** When HTF bias is added, it forces trades to ONLY follow the D1/H4 institutional trend. Suddenly, London and NY momentum becomes an asset rather than a hazard, transforming -$794.73 into **+$957.95**!
3. **Strategic Rule:** Session filtering is toxic in isolation, but essential when paired with higher-timeframe trend alignment.

---

## 6. Directional Bias Analysis (Long vs Short)

| Direction | Trades | Win Rate | Gross Profit | Gross Loss | Net P&L | Profit Factor | Expectancy |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **BULLISH (Long)** | 42 | 38.1% | $1,235.98 | $1,124.69 | +$111.29 | 1.099 | +$2.65 |
| **BEARISH (Short)** | 46 | 37.0% | $1,574.61 | $1,264.32 | +$310.29 | 1.246 | +$6.75 |

Both directions showed positive net profitability. The strategy does not suffer from single-direction long-only bias.
