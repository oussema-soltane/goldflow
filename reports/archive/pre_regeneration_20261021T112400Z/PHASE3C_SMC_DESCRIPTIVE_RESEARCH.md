# GoldFlow Phase 3C — Pure-SMC Descriptive Research Report

**Generated (UTC):** 2026-10-20T14:49:28.414268+00:00  
**Research Scope:** Pure-SMC Descriptive Event Statistics and Setup Hypothesis Excursion Analysis  
**Status:** Complete on Verified Real MetaTrader 5 Data  
**Compliance:** Look-Ahead-Free Reference Entry (Next-Bar Open), Zero ML, No Simulated Orders/Fills

---

## 1. Executive Summary

Phase 3C establishes the first empirical descriptive baseline of GoldFlow's primary **Pure Smart Money Concepts (SMC)** framework using genuine, verified tick-synchronized MetaTrader 5 historical data for **XAUUSD**. All datasets passed the Phase 3B data readiness audit with zero critical blockers, explicit `server_wall_clock` conversion via `Europe/Athens`, and raw MT5 epoch integer preservation.

### Key Research Findings
1. **Event Abundance vs. Setup Selectivity:**
   - Across the 20,000 combined bars (5,000 H4, 5,000 H1, 5,000 M15, 5,000 M5), the Pure-SMC engine detected **5,368 confirmed swing fractals**, **1,881 structure breaks**, **1,403 equal-level liquidity pools**, **1,300 liquidity sweeps**, and **1,830 break-confirmed order blocks**.
   - Despite the high density of constituent events, the sequential hypothesis (**Liquidity Sweep → Opposite CHoCH → Order-Block Retest/Rejection**) acts as a disciplined filter: producing **15 setups on H4**, **30 on H1**, **49 on M15**, and **42 on M5** (136 total setups across all timeframes).

2. **Directional Symmetry:**
   - Setup distribution was well-balanced across bullish and bearish candidates: H4 (8 Long / 7 Short), H1 (17 Long / 13 Short), M15 (21 Long / 28 Short), M5 (22 Long / 20 Short). Total: **68 Long vs. 68 Short** (136 total).

3. **Forward Excursion Profiles (Look-Ahead Free Next-Bar Open):**
   - Measuring excursion strictly from the opening price of the candle immediately following the rejection close (`signal_index + 1`) eliminates intrabar execution bias.
   - On **M5**, median MFE reaches **$4.22** (0.95 ATR) at 30m (6b) and **$11.21** (2.75 ATR) at 4h (48b), with **50.0%** favorable closes at 4h (48b).
   - On **M15**, median MFE reaches **$6.16** (0.75 ATR) at 1h (4b) and **$25.73** (2.85 ATR) at 8h (32b), with **53.1%** favorable closes at 8h (32b).
   - On **H1**, median MFE reaches **$14.60** (0.79 ATR) at 4h (4b) and **$36.70** (1.93 ATR) at 24h (24b), with **50.0%** favorable closes at 24h (24b).
   - On **H4**, median MFE reaches **$23.72** (1.18 ATR) at 24h (6b) and **$39.53** (4.46 ATR) at 120h (30b), with **53.3%** favorable closes at 120h (30b).

4. **Edge-Censoring Accounting:**
   - Of the 136 total candidates, 0 observations were edge-censored across tested forward horizon windows.

---

## 2. Ingested Dataset Provenance & Coverage

| Timeframe | File | Bars | Date Range (UTC) | Broker Server | Mode / Timezone | Provenance Status |
|---|---|---:|---|---|---|---|
| **H4** | `XAUUSD_H4_clean.csv` | 5000 | 2023-07-26 → 2026-10-19 | MetaQuotes-Demo | `server_wall_clock` (Europe/Athens) | VERIFIED (Real MT5) |
| **H1** | `XAUUSD_H1_clean.csv` | 5000 | 2025-12-05 → 2026-10-20 | MetaQuotes-Demo | `server_wall_clock` (Europe/Athens) | VERIFIED (Real MT5) |
| **M15** | `XAUUSD_M15_clean.csv` | 5000 | 2026-07-31 → 2026-10-20 | MetaQuotes-Demo | `server_wall_clock` (Europe/Athens) | VERIFIED (Real MT5) |
| **M5** | `XAUUSD_M5_clean.csv` | 5000 | 2026-09-22 → 2026-10-19 | MetaQuotes-Demo | `server_wall_clock` (Europe/Athens) | VERIFIED (Real MT5) |

> [!NOTE]
> All datasets originate from interactive MetaTrader 5 build 6259 on `MetaQuotes-Demo`. Raw POSIX epochs were preserved in `time_raw_epoch` and converted using dynamic DST-aware local wall-clock localization (`Europe/Athens`). Zero synthetic data was used in this research.

---

## 3. Pure-SMC Event Distribution

Constituent events were detected strictly in accordance with `docs/SMC_RULES.md`.

| Timeframe | Swings (High/Low) | Structure Breaks | BOS | CHoCH | Liquidity Pools | Liquidity Sweeps | Order Blocks |
|---|---:|---:|---:|---:|---:|---:|---:|
| **H4** | 1386 (703L / 683H) | 471 | 258 | 213 | 181 | 152 | 465 |
| **H1** | 1373 (703L / 670H) | 472 | 241 | 231 | 276 | 257 | 456 |
| **M15** | 1310 (666L / 644H) | 466 | 230 | 236 | 417 | 387 | 451 |
| **M5** | 1299 (657L / 642H) | 472 | 245 | 227 | 529 | 504 | 458 |

### Event Breakdown by Session (Confirmation Time)

| Timeframe | Asia (22-08 UTC) | London (08-12 UTC) | NY AM (12-17 UTC) | NY PM (17-21 UTC) | Total Events |
|---|---:|---:|---:|---:|---:|
| **H4** | 923 | 488 | 486 | 758 | 2655 |
| **H1** | 1229 | 488 | 735 | 382 | 2834 |
| **M15** | 1396 | 558 | 695 | 382 | 3031 |
| **M5** | 1470 | 580 | 754 | 458 | 3262 |

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
| Total Bars Evaluated | 5000 | 5000 | 5000 | 5000 | **20000** |
| Total Structure Breaks | 471 | 472 | 466 | 472 | **1881** |
| CHoCH Breaks Evaluated | 213 | 231 | 236 | 227 | **907** |
| Trend-Aligned CHoCH | 213 | 231 | 236 | 227 | **907** |
| Preceding Sweep within 20b | 61 | 99 | 132 | 156 | **448** |
| Identifiable Order Block | 60 | 97 | 128 | 147 | **432** |
| Retest Attempt Evaluated | 60 | 97 | 128 | 147 | **432** |
| Retest Invalidated (Close past far edge) | 17 | 19 | 23 | 31 | **90** |
| Retest Timed Out (> 20b) | 21 | 31 | 27 | 44 | **123** |
| Retest Rejection Confirmed | 22 | 47 | 78 | 72 | **219** |
| Valid Risk & RR (>= 1.0) | 15 | 30 | 49 | 42 | **136** |
| Final Setup Candidates | 15 | 30 | 49 | 42 | **136** |
| Next-Bar Open Available | 15 | 30 | 49 | 42 | **136** |

### Setup Candidates by Direction and Session

| Timeframe | Long Candidates | Short Candidates | Asia | London | NY AM | NY PM | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| **H4** | 8 | 7 | 3 | 3 | 6 | 3 | **15** |
| **H1** | 17 | 13 | 15 | 3 | 11 | 1 | **30** |
| **M15** | 21 | 28 | 23 | 6 | 15 | 5 | **49** |
| **M5** | 22 | 20 | 18 | 7 | 11 | 6 | **42** |

---

## 5. Forward Price Excursion Statistics (MFE / MAE)

All measurements use **Next-Bar Open** as the reference price and baseline ATR (period 14) computed strictly up to the signal close.

### M5 Forward Excursions (N = 42)

| Horizon | Complete / Censored | MFE ($) Mean ± Std | MFE ($) Median [IQR] | MAE ($) Mean ± Std | MAE ($) Median [IQR] | MFE (ATR) Median | MAE (ATR) Median | Favorable Close % | MFE > MAE % |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| **30m (6b)** | 42 / 0 | $4.95 ± 4.23 | $4.22 [$1.81, $6.78] | $5.64 ± 8.20 | $3.09 [$1.23, $6.49] | 0.95 | 0.83 | 54.8% | 50.0% |
| **1h (12b)** | 42 / 0 | $6.77 ± 6.07 | $4.78 [$2.41, $10.20] | $7.53 ± 8.70 | $5.86 [$2.18, $9.93] | 1.35 | 1.38 | 52.4% | 45.2% |
| **2h (24b)** | 42 / 0 | $10.86 ± 11.04 | $7.93 [$3.44, $13.32] | $11.88 ± 12.00 | $9.87 [$3.35, $15.32] | 2.27 | 2.40 | 42.9% | 47.6% |
| **4h (48b)** | 42 / 0 | $14.46 ± 12.11 | $11.21 [$6.49, $22.15] | $16.61 ± 12.48 | $14.74 [$8.77, $20.56] | 2.75 | 3.62 | 50.0% | 45.2% |

### M15 Forward Excursions (N = 49)

| Horizon | Complete / Censored | MFE ($) Mean ± Std | MFE ($) Median [IQR] | MAE ($) Mean ± Std | MAE ($) Median [IQR] | MFE (ATR) Median | MAE (ATR) Median | Favorable Close % | MFE > MAE % |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| **1h (4b)** | 49 / 0 | $8.26 ± 6.55 | $6.16 [$3.65, $12.13] | $9.17 ± 9.23 | $6.13 [$3.15, $11.66] | 0.75 | 0.69 | 49.0% | 49.0% |
| **2h (8b)** | 49 / 0 | $12.11 ± 9.99 | $8.42 [$4.81, $17.04] | $13.05 ± 12.67 | $10.16 [$4.86, $15.59] | 0.97 | 1.20 | 51.0% | 42.9% |
| **4h (16b)** | 49 / 0 | $19.44 ± 15.27 | $13.84 [$6.19, $31.42] | $16.33 ± 13.94 | $12.32 [$6.97, $20.38] | 1.63 | 1.55 | 53.1% | 55.1% |
| **8h (32b)** | 49 / 0 | $27.89 ± 19.16 | $25.73 [$12.64, $38.22] | $25.28 ± 22.71 | $15.70 [$9.01, $35.91] | 2.85 | 2.13 | 53.1% | 55.1% |

### H1 Forward Excursions (N = 30)

| Horizon | Complete / Censored | MFE ($) Mean ± Std | MFE ($) Median [IQR] | MAE ($) Mean ± Std | MAE ($) Median [IQR] | MFE (ATR) Median | MAE (ATR) Median | Favorable Close % | MFE > MAE % |
|---|---:|---|---|---|---|---:|---:|---:|---:|
| **4h (4b)** | 30 / 0 | $22.52 ± 21.73 | $14.60 [$9.98, $25.81] | $18.37 ± 15.73 | $14.24 [$7.78, $25.96] | 0.79 | 0.69 | 50.0% | 53.3% |
| **8h (8b)** | 30 / 0 | $29.08 ± 28.63 | $21.83 [$10.65, $34.67] | $25.07 ± 22.10 | $17.27 [$10.14, $33.94] | 1.11 | 0.92 | 53.3% | 53.3% |
| **16h (16b)** | 30 / 0 | $35.63 ± 28.84 | $30.57 [$15.07, $50.45] | $36.64 ± 29.27 | $25.85 [$15.74, $44.23] | 1.64 | 1.38 | 43.3% | 56.7% |
| **24h (24b)** | 30 / 0 | $45.92 ± 35.11 | $36.70 [$22.93, $67.20] | $43.78 ± 31.40 | $34.20 [$18.39, $67.13] | 1.93 | 2.02 | 50.0% | 53.3% |

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

- **Common Window Start (UTC):** `2026-09-22T23:15:00+00:00`
- **Common Window End (UTC):** `2026-10-19T13:00:00+00:00`
- **Span:** ~27 calendar days (~20 active Gold trading days)

| Timeframe | Bars in Window | Swings | Structure Breaks (BOS / CHoCH) | Liquidity Pools | Sweeps | Order Blocks | Setups (Long / Short) |
|---|---:|---:|---:|---:|---:|---:|---:|
| **H4** | 112 | 31 | 9 (3 / 6) | 4 | 3 | 10 | **0** (0L / 0S) |
| **H1** | 410 | 114 | 35 (16 / 19) | 17 | 16 | 32 | **1** (1L / 0S) |
| **M15** | 1640 | 426 | 160 (80 / 80) | 135 | 128 | 154 | **20** (10L / 10S) |
| **M5** | 4918 | 1274 | 462 (239 / 223) | 516 | 498 | 449 | **42** (22L / 20S) |

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
