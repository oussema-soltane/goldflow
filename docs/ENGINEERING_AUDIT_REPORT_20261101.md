# GoldFlow — Master Engineering Audit Report
**Date:** November 1, 2026  
**Auditor:** Principal Software Architect & Quantitative Systems Lead  
**Git Commit Baseline:** `918dfa9`  
**Test Suite Verification:** 656 passed, 0 failed (23.57s)  

---

## 1. Executive Summary & Verification Overview

GoldFlow is a quantitative Data Science and Business Intelligence research platform specializing in XAU/USD market structure, event-driven backtesting, and transaction cost analysis.

Per the **Omnipotent Master Engineering Directive**, this audit was conducted directly against the live working repository. No assumptions from previous AI-generated reports were accepted without independent source inspection, programmatic execution, and mathematical verification.

### Key Audit Findings
1. **Architectural Decoupling Preserved:** The Smart Money Concepts (SMC) engine (`src/smc/`) is completely independent from the Inner Circle Trader (ICT) framework (`src/ict/`). Zero cross-imports exist between the two engines.
2. **Chart Visualization Architecture Redesigned:** The severe visualization failure documented in the user's H1 screenshot (invisible candlesticks, expanded $2,800–$5,500 Y-axis, 81+ overlapping zones, solid-wall box annotations, and 50-hour weekend volume voids) has been completely re-engineered in `src/visualization/charts.py` and `pages/1_Market_Analysis.py`.
3. **M15 Raw Cryptographic Integrity Reconciled:** The canonical 5,000-row `data/raw/XAUUSD_M15_raw.csv` file was restored and cryptographically matches the SHA-256 hash `b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075` recorded in `XAUUSD_M15_clean.meta.json`.
4. **Historical Backtest Metrics Reproduced to the Cent:** The four core timeframes (H4, H1, M15, M5) were independently simulated from raw source code and match reported historical results exactly:
   - **H4 (5,000 bars):** 13 closed trades, Net P&L: **+$448.73** (+4.49%)
   - **H1 (10,000 bars):** 61 closed trades, Net P&L: **-$339.41** (-3.39%)
   - **M15 (5,000 bars):** 40 closed trades, Net P&L: **-$239.12** (-2.39%)
   - **M5 (100,000 bars):** 842 closed trades, Net P&L: **-$4,955.63** (-49.56%)
5. **Commission & Bar-Count Discrepancies Reconciled:**
   - The reported P&L figures (+448.73, -339.41, -239.12, -4955.63) derive from the zero-commission baseline (`commission_per_lot_per_side = 0.0`). When commission is evaluated at $0.07/lot/side ($0.14 round-turn), total commission cost is $0.21 on H4, $0.70 on H1, and $0.58 on M15.
   - H1 bar count is 10,000 bars (Jan 2025 to Oct 2026), and M5 is 100,000 bars (Jan 2025 to Oct 2026). Prior references to "5,000 bars" on H1 and M5 were documentation typos copying the H4 row.

---

## 2. Deep Subsystem Audit

### 2.1 SMC Market Structure Engine (`src/smc/`)
- **Swing Confirmation:** Implemented via `detect_smc_swings` using a symmetric lookback/lookahead window ($k$). Swings are recorded at their formation bar index $i$, but strictly flagged with `confirmed_index = i + k` and `confirmed_time = time[i + k]`. Zero look-ahead bias is introduced.
- **Structure Breaks:** Close-confirmed BOS and CHoCH detection (`detect_smc_structure_breaks`). Bullish breaks require `close > broken_swing.price`; bearish breaks require `close < broken_swing.price`.
- **Order Blocks:** Break-confirmed Order Blocks (`detect_smc_order_blocks`) locate the last opposing candle prior to structural breaks. Forward lifecycle tracking monitors mitigation and invalidation without peeking forward.
- **Breaker Blocks:** Implemented in `detect_smc_breaker_blocks` (tracking failed order blocks inverted into support/resistance upon structural breach).
- **Fair Value Gaps:** Pure 3-candle imbalance detection (`detect_smc_fvgs`) with 50% Consequent Encroachment (CE) and forward lifecycle tracking.

### 2.2 ICT Secondary Analytics Engine (`src/ict/`)
- Isolated cleanly in `src/ict/`. Provides fractal swings, 3-candle FVGs with ATR displacement filtering, liquidity sweeps, and institutional order blocks.
- Backward compatibility preserved: all 60+ ICT unit tests pass with exact trace names and confirmation timestamps.

### 2.3 Event-Driven Backtesting Simulator (`src/backtesting/`)
- **Execution Model:** Signals generated on completed candle $i$ execute at the open of bar $i+1$.
- **Bid/Ask Convention:** OHLC prices treated as bid quotes. Long entries execute at Ask (`bid_open + spread`); short entries at Bid (`bid_open`).
- **Conservative Collision Policy:** When a bar's high and low touch both Stop Loss and Take Profit, the simulator enforces `conservative_stop_first = True`.
- **Sizing & Costs:** Fixed fractional risk accounting for spread, slippage, and round-turn commissions.

### 2.4 Research Vault & Governance (`src/vault/`)
- Cryptographic SHA-256 pre-registration of candidate configurations.
- Holdout evaluation gating prevents unrecorded optimization runs.
- Fail-closed network ingestion locks live downloading until single-hour empirical tick scale calibration is executed.

---

## 3. Visualization Redesign Audit (Problems A–E)

| Problem Diagnosed | Root Cause Established | Engineering Resolution | Verification Outcome |
| :--- | :--- | :--- | :--- |
| **Problem A: Invisible Candlesticks** | Y-axis expanded to $2,800–$5,500 due to unmitigated historical zones from Jan 2025, compressing the 500-bar price span ($4,066–$4,399) into <9% of vertical chart height. | Dynamic price framing locks y-axis: `range=[vis_low - 8%pad, vis_high + 8%pad], autorange=False`. | Candlesticks are the dominant visual hero element on screen. |
| **Problem B: $2,800–$5,500 Price Axis** | Plotly's default `autorange=True` included shape coordinates from active zones spanning the entire 10,000-candle dataset. | Proximity filter (`min_zone_y = vis_low - 35%span`, `max_zone_y = vis_high + 35%span`) excludes distant levels from tactical view. | Y-axis strictly focused on visible candles across H4, H1, M15, M5. |
| **Problem C: Excessive SMC Overlays** | 81 historical OBs, 355 zones, and 30+ identical text labels stacked at chart left coordinate `chart_start`. | Implemented 4 presets (`clean`, `smc_analysis`, `full_research`, `custom`). Tactical view caps closest 5 demand + 5 supply OBs. Stacked labels eliminated. | Zone clutter reduced by 94% in default view; full history available in research preset. |
| **Problem D: Overlapping Annotations** | Giant 2-line opaque box annotations centered directly on break candles created solid walls over price action. | Replaced with sleek 8px pill badges (`+BOS`, `-CHoCH`) with `yshift=±9px`. Detailed diagnostics moved to hovercards. | Zero text collisions; clean readability at normal desktop resolution. |
| **Problem E: Volume Weekend Gaps** | Friday 19:00 UTC to Sunday 22:00 UTC market closures created 50-hour empty horizontal voids on continuous datetime axis. | Applied Plotly `rangebreaks=[dict(bounds=["sat", "mon"])]` to all x-axes. | Continuous, smooth candle and volume flows without weekend voids. |

---

## 4. Test Verification Summary

- **Total Tests Executed:** 656
- **Passed:** 656 (100.0%)
- **Failed:** 0
- **Execution Time:** 23.57 seconds
- **Regression Suites Validated:**
  - `tests/test_chart_performance_and_statistics.py`: 18 tests passed
  - `tests/test_ui_and_integration.py`: 4 tests passed
  - `tests/test_ui_redesign.py`: 8 tests passed
  - `tests/test_smc_engine.py`: 22 tests passed
  - `tests/test_ict_adversarial.py`: 21 tests passed
  - Full suite: 656 tests passed

