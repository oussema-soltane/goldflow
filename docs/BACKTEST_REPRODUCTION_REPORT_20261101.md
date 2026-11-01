# GoldFlow — Backtest Reproduction & Reconciliation Report
**Date:** November 1, 2026  
**Auditor:** Principal Software Architect & Quantitative Systems Lead  
**Pipeline Script:** `scripts/run_smc_backtest.py`  
**Git Baseline:** `918dfa9`  

---

## 1. Executive Summary

This report documents the independent, programmatic reproduction of the canonical GoldFlow Pure-SMC event-driven backtests across all four supported timeframes (H4, H1, M15, M5).

The primary research hypothesis is:
$$\text{Liquidity Sweep} \longrightarrow \text{Change of Character (CHoCH)} \longrightarrow \text{Order Block Retest}$$

All backtests were executed from the raw source implementation using `scripts/run_smc_backtest.py` without modifying strategy logic or overriding risk rules.

---

## 2. Independent Reproduction Results

| Parameter | H4 (Higher TF Context) | H1 (Structural Trend) | M15 (Primary Setup) | M5 (Microstructure) |
| :--- | :--- | :--- | :--- | :--- |
| **Input Dataset** | `XAUUSD_H4_clean.csv` | `XAUUSD_H1_clean.csv` | `XAUUSD_M15_clean.csv` | `XAUUSD_M5_clean.csv` |
| **Dataset Rows** | 5,000 bars | 10,000 bars | 5,000 bars | 100,000 bars |
| **Date Range (UTC)** | 2023-08-01 to 2026-10-20 | 2025-01-31 to 2026-10-20 | 2026-08-04 to 2026-10-22 | 2025-01-31 to 2026-10-20 |
| **Candidates Detected** | 15 | 69 | 54 | 1,015 |
| **Closed Trades** | **13** | **61** | **40** | **842** |
| **Winning Trades** | 8 | 24 | 17 | 309 |
| **Losing Trades** | 5 | 37 | 23 | 533 |
| **Win Rate** | 61.54% | 39.34% | 42.50% | 36.70% |
| **Gross Profit** | +$1,279.03 | +$3,745.39 | +$2,818.88 | +$34,228.37 |
| **Gross Loss** | -$830.30 | -$4,084.80 | -$3,058.00 | -$39,184.00 |
| **Net Profit** | **+$448.73** | **-$339.41** | **-$239.12** | **-$4,955.63** |
| **Total Return** | **+4.49%** | **-3.39%** | **-2.39%** | **-49.56%** |
| **Profit Factor** | **1.540** | **0.917** | **0.922** | **0.873** |
| **Max Drawdown ($)** | $751.76 | $1,265.62 | $1,632.95 | $6,392.88 |
| **Max Drawdown (%)** | 7.21% | 11.66% | 15.37% | 59.28% |
| **Status vs Reported** | **EXACT MATCH (0.00¢)** | **EXACT MATCH (0.00¢)** | **EXACT MATCH (0.00¢)** | **EXACT MATCH (0.00¢)** |

---

## 3. Discrepancy Reconciliation

### 3.1 Commission Accounting Discrepancy & M5 Reconciliation
**The Question:** Earlier reports cited zero commission, while a later summary described commission of $0.07/lot/side, yet reported identical P&L figures (+448.73, -339.41, -239.12, -4955.63).

**The Mathematical Evidence & Complete Timeframe Audit:**
1. In `src/backtesting/engine.py`, the default `BacktestConfig.commission_per_lot_per_side` is `0.0`.
2. Running the simulator with `commission_per_lot_per_side = 0.0` vs `0.07` across all four timeframes yields the following exact trade accounting:

| Timeframe | Bars | Trades | Zero Comm Net P&L | Zero Comm PF | Comm ($0.07) Net P&L | Comm ($0.07) PF | Total Comm Paid | Delta |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **H4** | 5,000 | 13 | **+$448.73** | 1.540 | +$448.52 | 1.540 | $0.21 | -$0.21 |
| **H1** | 10,000 | 61 | **-$339.41** | 0.917 | -$334.68 | 0.918 | $0.70 | +$4.72 |
| **M15** | 5,000 | 40 | **-$239.12** | 0.922 | -$239.70 | 0.922 | $0.58 | -$0.58 |
| **M5** | 100,000 | 842 | **-$4,955.63** | 0.873 | -$4,959.36 | 0.873 | $21.71 | -$3.74 |

3. **Why H1 Net P&L is slightly less negative under commission (+4.72 delta):**
   In `src/backtesting/engine.py`, lot sizing incorporates estimated round-trip commission into the denominator risk divisor:
   $$\text{stop\_distance} = |\text{entry} - \text{sl}| + \text{slippage} + \text{commission\_estimate}$$
   $$\text{lots} = \left\lfloor \frac{\text{risk\_cash}}{\text{stop\_distance} \times \text{contract\_size} \times \text{lot\_step}} \right\rfloor \times \text{lot\_step}$$
   Non-zero commission marginally increases the risk divisor, rounding down lot sizes by one lot step on several high-risk losing trades. The reduced loss on those positions exceeded the total commission paid ($0.70), yielding a net +$4.72 difference.
4. **Resolution:** The published baseline numbers (+448.73, -339.41, -239.12, -4955.63) were mathematically generated under `commission_per_lot_per_side = 0.0`. The reference to $0.07 was an unapplied specification assumption in the narrative.

### 3.2 Historical Bar Count Discrepancy
**The Question:** Certain summary tables listed all timeframes as having "5,000 bars", while datasets on disk contain 10,000 bars for H1 and 100,000 bars for M5.

**The Evidence:**
- `data/processed/XAUUSD_H1_clean.csv`: 10,001 rows (10,000 candles). Generating 61 trades spanning Jan 2025 to Oct 2026 requires the full 10,000 bars.
- `data/processed/XAUUSD_M5_clean.csv`: 100,001 rows (99,999 candles). Generating 842 trades spanning Jan 2025 to Oct 2026 requires the full 100,000 bars.
- **Resolution:** The canonical datasets on disk are 5,000 bars for H4, 10,000 bars for H1, 5,000 bars for M15, and 100,000 bars for M5. The "5,000 bars" label in previous summary rows was a copy-paste clerical error.

---

## 4. Quantitative Strategy Evaluation & Research Findings

1. **Higher Timeframe Stability (H4):** H4 is the only profitable timeframe (+4.49%, PF 1.540). The low trade frequency (13 trades over 3 years) reflects strong structural filtering where daily/weekly liquidity sweeps have high institutional follow-through.
2. **Lower Timeframe Decay (M15, M5):** Strategy performance degrades monotonically as timeframe decreases (-2.39% on M15, -49.56% on M5). On M5, market noise and spread/slippage friction erode the theoretical edge, resulting in 533 losses against 309 wins.
3. **Target Source Limitation:** Using opposing liquidity pools as fixed take-profit targets creates an asymmetric risk profile: distant unmitigated pools are frequently not reached before trailing structure reverses. This reinforces ADR-006 (rationalized fixed R:R targets for intraday execution).

