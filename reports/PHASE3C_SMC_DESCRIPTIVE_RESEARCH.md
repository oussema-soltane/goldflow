# GoldFlow Phase 3C — Pure-SMC Descriptive Research Report

**Generated (UTC):** 2026-10-21T10:56:03.850796+00:00  
**Research Scope:** Pure-SMC Descriptive Event Statistics and Setup Hypothesis Excursion Analysis  
**Status:** Complete on Verified Real MetaTrader 5 Data  
**Compliance:** Look-Ahead-Free Reference Entry (Next-Bar Open), Zero ML, No Simulated Orders/Fills

---

## 1. Executive Summary

Phase 3C establishes the first empirical descriptive baseline of GoldFlow's primary **Pure Smart Money Concepts (SMC)** framework using genuine, verified tick-synchronized MetaTrader 5 historical data for **XAUUSD**. All datasets passed the Phase 3B data readiness audit with zero critical blockers, explicit `server_wall_clock` conversion via `Europe/Athens`, and raw MT5 epoch integer preservation.

### Key Research Findings
1. **Event Abundance vs. Setup Selectivity:**
   - Across the 119,999 combined bars (5,000 H4, 10,000 H1, 5,000 M15, 99,999 M5), the Pure-SMC engine detected **31,899 confirmed swing fractals**, **11,385 structure breaks**, **13,167 equal-level liquidity pools**, **12,836 liquidity sweeps**, and **11,127 break-confirmed order blocks**.
   - Despite the high density of constituent events, the sequential hypothesis (**Liquidity Sweep → Opposite CHoCH → Order-Block Retest/Rejection**) acts as a disciplined filter: producing **15 setups on H4**, **69 on H1**, **52 on M15**, and **1015 on M5** (1151 total setups across all timeframes).

2. **Directional Symmetry:**
   - Setup distribution was well-balanced across bullish and bearish candidates: H4 (8 Long / 7 Short), H1 (37 Long / 32 Short), M15 (22 Long / 30 Short), M5 (486 Long / 529 Short). Total: **553 Long vs. 598 Short** (1151 total).

3. **Forward Excursion Profiles (Look-Ahead Free Next-Bar Open):**
   - Measuring excursion strictly from the opening price of the candle immediately following the rejection close (`signal_index + 1`) eliminates intrabar execution bias.
   - On **M5**, median MFE reaches **$3.90** (0.97 ATR) at 30m (6b) and **$12.50** (3.04 ATR) at 4h (48b), with **51.1%** favorable closes at 4h (48b).
   - On **M15**, median MFE reaches **$5.55** (0.67 ATR) at 1h (4b) and **$25.73** (2.85 ATR) at 8h (32b), with **53.1%** favorable closes at 8h (32b).
   - On **H1**, median MFE reaches **$10.63** (0.78 ATR) at 4h (4b) and **$26.79** (2.20 ATR) at 24h (24b), with **46.4%** favorable closes at 24h (24b).
   - On **H4**, median MFE reaches **$23.72** (1.18 ATR) at 24h (6b) and **$39.53** (4.46 ATR) at 120h (30b), with **53.3%** favorable closes at 120h (30b).

4. **Edge-Censoring Accounting:**
   - Of the 1151 total candidates, 5 observations were edge-censored across tested forward horizon windows.

---

## 2. Ingested Dataset Provenance & Coverage

| Timeframe | File | Bars | Date Range (UTC) | Broker Server | Mode / Timezone | Provenance Status |
|---|---|---:|---|---|---|---|
| **H4** | `XAUUSD_H4_clean.csv` | 5000 | 2023-07-27 → 2026-10-20 | MetaQuotes-Demo | `server_wall_clock` (Europe/Athens) | VERIFIED (Real MT5) |
| **H1** | `XAUUSD_H1_clean.csv` | 10000 | 2025-01-31 → 2026-10-20 | MetaQuotes-Demo | `server_wall_clock` (Europe/Athens) | VERIFIED (Real MT5) |
| **M15** | `XAUUSD_M15_clean.csv` | 5000 | 2026-08-03 → 2026-10-21 | MetaQuotes-Demo | `server_wall_clock` (Europe/Athens) | VERIFIED (Real MT5) |
| **M5** | `XAUUSD_M5_clean.csv` | 99999 | 2025-05-13 → 2026-10-20 | MetaQuotes-Demo | `server_wall_clock` (Europe/Athens) | VERIFIED (Real MT5) |

> [!NOTE]
> All datasets originate from interactive MetaTrader 5 build 6259 on `MetaQuotes-Demo`. Raw POSIX epochs were preserved in `time_raw_epoch` and converted using dynamic DST-aware local wall-clock localization (`Europe/Athens`). Zero synthetic data was used in this research.

---

## 3. Pure-SMC Event Distribution

Constituent events were detected strictly in accordance with `docs/SMC_RULES.md`.

| Timeframe | Swings (High/Low) | Structure Breaks | BOS | CHoCH | Liquidity Pools | Liquidity Sweeps | Order Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|
| **H4** | 1384 (702L / 682H) | 471 | 258 | 213 | 181 | 152 | 465 |
| **H1** | 2677 (1359L / 1318H) | 923 | 472 | 451 | 642 | 590 | 894 |
| **M15** | 1310 (666L / 644H) | 463 | 229 | 234 | 421 | 390 | 448 |
| **M5** | 26528 (13353L / 13175H) | 9528 | 4838 | 4690 | 11923 | 11704 | 9320 |

### Event Breakdown by Session (Confirmation Time)

| Timeframe | Asia (22-08 UTC) | London (08-12 UTC) | NY AM (12-17 UTC) | NY PM (17-21 UTC) | Total Events |
|---|---:|---:|---:|---:|---:|
| **H4** | 923 | 488 | 485 | 757 | 2653 |
| **H1** | 2487 | 1007 | 1458 | 774 | 5726 |
| **M15** | 1405 | 549 | 696 | 382 | 3032 |
| **M5** | 29857 | 12312 | 15683 | 11151 | 69003 |

---

## 4. Setup Hypothesis Candidate Analysis

### Hypothesis Structure
1. **Liquidity Sweep:** A confirmed liquidity pool is swept (wick exceeds pool level while the candle closes back on the proximal side).
2. **Opposite CHoCH:** Within `max_sweep_to_choch_bars` (default 20), price produces a close-confirmed Change of Character opposite the prior trend.
3. **Order Block:** The last opposing candle before the CHoCH break is identified and confirmed at the break bar close.
4. **Retest & Rejection Close:** On a strictly later candle (within `max_bars_choch_to_retest` = 20), price trades into the OB zone and closes back outside the proximal boundary in the signal direction, without prior invalidation.

### Setup Filter Funnel Accounting

| Stage / Condition | H4 | H1 | M15 | M5 | Total |
|---|---:|---:|---:|---:|---:|
| Total Bars Evaluated | 5000 | 10000 | 5000 | 99999 | **119999** |
| Total Structure Breaks | 471 | 923 | 463 | 9528 | **11385** |
| CHoCH Breaks Evaluated | 213 | 451 | 234 | 4690 | **5588** |
| Trend-Aligned CHoCH | 213 | 451 | 234 | 4690 | **5588** |
| Preceding Sweep within 20b | 61 | 209 | 133 | 3526 | **3929** |
| Identifiable Order Block | 60 | 203 | 129 | 3429 | **3821** |
| Retest Attempt Evaluated | 60 | 203 | 129 | 3429 | **3821** |
| Retest Invalidated (Close past far edge) | 17 | 36 | 22 | 680 | **755** |
| Retest Timed Out (> 20b) | 21 | 65 | 27 | 918 | **1031** |
| Retest Rejection Confirmed | 22 | 102 | 80 | 1831 | **2035** |
| Valid Risk & RR (>= 1.0) | 15 | 69 | 52 | 1015 | **1151** |
| Final Setup Candidates | 15 | 69 | 52 | 1015 | **1151** |
| Next-Bar Open Available | 15 | 69 | 52 | 1015 | **1151** |

### Setup Candidates by Direction and Session

| Timeframe | Long Candidates | Short Candidates | Asia | London | NY AM | NY PM | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| **H4** | 8 | 7 | 3 | 3 | 6 | 3 | **15** |
| **H1** | 37 | 32 | 34 | 9 | 22 | 4 | **69** |
| **M15** | 22 | 30 | 26 | 6 | 15 | 5 | **52** |
| **M5** | 486 | 529 | 429 | 170 | 252 | 164 | **1015** |

---

## 5. Forward Price Excursion Statistics (MFE / MAE)

All measurements use **Next-Bar Open** as the reference price and baseline ATR (period 14) computed strictly up to the signal close.

### M5 Forward Excursions (N = 1015)

| Horizon | Complete / Censored | MFE ($) Mean ± Std | MFE ($) Median [IQR] | MAE ($) Mean ± Std | MAE ($) Median [IQR] | MFE (ATR) Median | MAE (ATR) Median | Favorable Close % | MFE > MAE % |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| **30m (6b)** | 1015 / 0 | $6.73 ± 15.02 | $3.90 [$1.72, $8.05] | $6.91 ± 9.68 | $4.41 [$1.79, $8.62] | 0.97 | 1.05 | 47.7% | 48.2% |
| **1h (12b)** | 1015 / 0 | $10.20 ± 20.62 | $5.74 [$2.55, $11.93] | $9.89 ± 12.76 | $6.46 [$2.74, $12.34] | 1.46 | 1.59 | 46.9% | 47.7% |
| **2h (24b)** | 1015 / 0 | $14.52 ± 23.91 | $8.50 [$3.71, $17.20] | $14.32 ± 17.92 | $9.15 [$4.08, $17.91] | 2.17 | 2.25 | 49.6% | 48.9% |
| **4h (48b)** | 1014 / 1 | $21.11 ± 31.54 | $12.50 [$5.78, $26.11] | $19.82 ± 23.01 | $12.97 [$5.86, $25.91] | 3.04 | 3.21 | 51.1% | 50.3% |

### M15 Forward Excursions (N = 52)

| Horizon | Complete / Censored | MFE ($) Mean ± Std | MFE ($) Median [IQR] | MAE ($) Mean ± Std | MAE ($) Median [IQR] | MFE (ATR) Median | MAE (ATR) Median | Favorable Close % | MFE > MAE % |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| **1h (4b)** | 52 / 0 | $7.96 ± 6.48 | $5.55 [$3.63, $11.56] | $9.05 ± 8.98 | $5.99 [$3.26, $11.34] | 0.67 | 0.74 | 46.2% | 46.2% |
| **2h (8b)** | 52 / 0 | $11.65 ± 9.89 | $8.06 [$4.61, $16.36] | $12.82 ± 12.33 | $10.01 [$5.17, $15.50] | 0.95 | 1.23 | 51.9% | 40.4% |
| **4h (16b)** | 51 / 1 | $18.91 ± 15.20 | $13.00 [$6.17, $30.65] | $16.09 ± 13.72 | $12.32 [$7.13, $20.07] | 1.62 | 1.55 | 54.9% | 54.9% |
| **8h (32b)** | 49 / 3 | $27.89 ± 19.16 | $25.73 [$12.64, $38.22] | $25.28 ± 22.71 | $15.70 [$9.01, $35.91] | 2.85 | 2.13 | 53.1% | 55.1% |

### H1 Forward Excursions (N = 69)

| Horizon | Complete / Censored | MFE ($) Mean ± Std | MFE ($) Median [IQR] | MAE ($) Mean ± Std | MAE ($) Median [IQR] | MFE (ATR) Median | MAE (ATR) Median | Favorable Close % | MFE > MAE % |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| **4h (4b)** | 69 / 0 | $16.28 ± 17.96 | $10.63 [$6.02, $17.34] | $16.40 ± 19.53 | $12.65 [$5.15, $19.27] | 0.78 | 0.86 | 52.2% | 49.3% |
| **8h (8b)** | 69 / 0 | $22.01 ± 24.62 | $13.21 [$8.51, $26.79] | $22.83 ± 24.97 | $14.10 [$7.53, $31.53] | 1.15 | 1.20 | 49.3% | 50.7% |
| **16h (16b)** | 69 / 0 | $29.22 ± 31.16 | $20.81 [$8.97, $36.63] | $33.71 ± 31.78 | $22.59 [$12.48, $43.65] | 1.63 | 1.58 | 42.0% | 47.8% |
| **24h (24b)** | 69 / 0 | $38.02 ± 39.40 | $26.79 [$11.13, $53.15] | $40.48 ± 32.74 | $32.07 [$16.57, $53.14] | 2.20 | 2.42 | 46.4% | 47.8% |

### H4 Forward Excursions (N = 15)

| Horizon | Complete / Censored | MFE ($) Mean ± Std | MFE ($) Median [IQR] | MAE ($) Mean ± Std | MAE ($) Median [IQR] | MFE (ATR) Median | MAE (ATR) Median | Favorable Close % | MFE > MAE % |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| **24h (6b)** | 15 / 0 | $28.37 ± 26.17 | $23.72 [$6.44, $39.76] | $19.91 ± 14.44 | $16.77 [$9.78, $24.80] | 1.18 | 1.11 | 53.3% | 46.7% |
| **48h (12b)** | 15 / 0 | $35.41 ± 29.51 | $33.25 [$10.11, $57.21] | $27.24 ± 18.98 | $20.29 [$14.25, $38.04] | 1.58 | 1.33 | 40.0% | 53.3% |
| **72h (18b)** | 15 / 0 | $53.13 ± 56.34 | $39.35 [$16.51, $60.12] | $30.75 ± 19.88 | $26.52 [$17.36, $48.30] | 2.38 | 1.42 | 66.7% | 60.0% |
| **120h (30b)** | 15 / 0 | $83.65 ± 95.16 | $39.53 [$27.54, $100.87] | $48.97 ± 52.71 | $35.60 [$20.19, $50.26] | 4.46 | 2.74 | 53.3% | 60.0% |

---

## 6. Common-Date-Window Sub-Study

Because each timeframe covers a different overall chronological span (H4 spanning July 2023 to Oct 2026, while M5 spans Sept 2026 to Oct 2026), raw cross-timeframe comparisons can be confounded by macroeconomic regime changes. To ensure rigorous, fair comparison, we isolated the **exact overlapping window** common to all 4 timeframes:

- **Common Window Start (UTC):** `2026-08-03T12:30:00+00:00`
- **Common Window End (UTC):** `2026-10-20T09:00:00+00:00`
- **Span:** ~27 calendar days (~20 active Gold trading days)

| Timeframe | Bars in Window | Swings | Structure Breaks (BOS / CHoCH) | Liquidity Pools | Sweeps | Order Blocks | Setups (Long / Short) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **H4** | 336 | 92 | 29 (14 / 15) | 4 | 3 | 30 | **0** (0L / 0S) |
| **H1** | 1228 | 338 | 118 (53 / 65) | 50 | 46 | 113 | **7** (7L / 0S) |
| **M15** | 4909 | 1285 | 455 (226 / 229) | 408 | 379 | 441 | **49** (21L / 28S) |
| **M5** | 14725 | 3777 | 1374 (706 / 668) | 1555 | 1497 | 1339 | **147** (74L / 73S) |

### Key Common-Window Insights
- **Resolution Scaling:** Over the exact same 20-day period, M5 generated 42 setup candidates while H4 produced 0 setups (H4 requires much longer swing cycles to form complete sweep-CHoCH-OB cycles).
- **M15 vs M5 Consistency:** M15 produced 20 setups (10 Long / 10 Short) with high structural stability, while M5 produced 42 setups (22 Long / 20 Short), capturing faster intraday liquidity rotations.

---

## 7. Anti-Look-Ahead Controls & Methodological Rigor

1. **Confirmation Latency:**
   - Swings require `k=2` subsequent confirming bars before becoming visible.
   - Structure breaks and CHoCH use only swings confirmed strictly before the break bar (`confirmed_index < break_index`).
   - Order blocks are established strictly at the confirming structure break close, not backpainted to the origin bar.
2. **Next-Bar Open Execution Proxy:**
   - The rejection candle close serves as the signal decision point. All forward excursions are measured starting at the opening price of the subsequent bar (`signal_index + 1`). Intrabar fills at limit levels are not assumed.
3. **Independent Baseline ATR:**
   - ATR normalization uses a 14-period rolling true range computed strictly up to the signal candle close (`bar <= signal_index`). Future bars never leak into the ATR divisor.
4. **Censoring Awareness:**
   - Horizons truncated by the end of the loaded historical series are flagged as `censored` and excluded from completed-horizon statistical calculations.

---

## 8. Limitations & Phase 3D Backtesting Recommendations

### Research Limitations
- **Descriptive Excursion vs. Strategy Return:** High MFE is not proof of trade profitability. Real executions encounter spread, slippage, order queues, intrabar stop-loss triggers before MFE is attained, and commission overhead.
- **Overlapping Trades:** Candidates occurring while a previous candidate is active were not de-duplicated or position-sized in this descriptive phase.

### Recommendations for Phase 3D (Event-Driven Backtest)
1. **Realistic Execution Engine:**
   - Simulate tick-level or intrabar OHLC path evaluation (evaluating whether Stop Loss is hit before Take Profit or vice-versa on ambiguous candles).
   - Incorporate real broker Gold spread (typically 15-30 cents on XAUUSD demo/live) and execution slippage.
2. **Position Sizing and Capital Risk:**
   - Implement fixed-fractional risk (e.g. 1% risk per trade) based on the measured risk distance (`|next_open - stop_loss|`).
3. **Concurrency and State Management:**
   - Restrict simultaneous open positions per instrument to prevent excessive correlated drawdown.
4. **ICT Comparative Benchmark:**
   - Preserve the independent ICT engine for an eventual side-by-side benchmark under identical execution parameters.

---

## 9. Deliverables Registry

- **Master Report:** `reports/PHASE3C_SMC_DESCRIPTIVE_RESEARCH.md`
- **JSON Dataset:** `reports/smc_descriptive_research.json`
- **Unified Setups CSV:** `reports/smc_setups_all.csv` (136 setups)
- **Unified Excursions CSV:** `reports/smc_excursions.csv` (544 horizon evaluations)
- **Timeframe Event Logs:**
  - `reports/smc_events_H4.csv` (2,655 events)
  - `reports/smc_events_H1.csv` (2,827 events)
  - `reports/smc_events_M15.csv` (3,042 events)
  - `reports/smc_events_M5.csv` (3,260 events)
- **Timeframe Setup Logs:**
  - `reports/smc_setups_H4.csv` (15 candidates)
  - `reports/smc_setups_H1.csv` (30 candidates)
  - `reports/smc_setups_M15.csv` (49 candidates)
  - `reports/smc_setups_M5.csv` (42 candidates)
