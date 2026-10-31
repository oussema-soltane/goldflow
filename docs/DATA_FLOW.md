# GOLDFLOW DATA FLOW ARCHITECTURE

This document charts the end-to-end data processing pipelines within GoldFlow, from raw market data ingestion through quantitative feature extraction, signal evaluation, execution simulation, and institutional presentation.

---

## 1. High-Level Data Flow Architecture

```
[Raw Historical Feeds]
 (MT5 CSV / Dukascopy bi5)
           │
           ▼
[src/data/cleaner.py & validator.py]
 ├── Check OHLC logic: High >= Open, Close, Low
 ├── Monotonic UTC Timestamps
 ├── Deduplicate & Fill/Flag Missing Bars
 └── Generate Data Quality Audit Report (JSON + MD)
           │
           ▼
[data/processed/XAUUSD_{TF}_clean.csv]
           │
  ┌────────┴────────────────────────────────────────┐
  │                                                 │
  ▼                                                 ▼
[SMC Engine: src/smc/engine.py]          [ICT Engine: src/ict/engine.py]
 ├── Swing Points (fractal window)        ├── Swings (fractal k)
 ├── Close Breaks (BOS / CHoCH)           ├── BOS / CHoCH
 ├── Liquidity Pools (tolerance bands)    ├── Liquidity Sweeps
 ├── Wick-and-Reclaim Sweeps              ├── Displacement Candles (ATR)
 ├── Break-Confirmed Order Blocks         ├── 3-Candle Displacement FVGs
 ├── Breaker Blocks (failed OBs)          └── Confirmed Order Blocks
 ├── 3-Candle Fair Value Gaps
 └── Swing Dealing Range (Equilibrium)
           │                                                 │
           ▼                                                 ▼
[SMC Analysis Result]                   [ICT Analysis Result]
           │                                                 │
  ┌────────┴───────────────────────────┐                     │
  │                                    │                     │
  ▼                                    ▼                     ▼
[Signal State Machine]          [Interactive Charts]   [Interactive Charts]
 (Sweep → CHoCH → Retest)        (src/visualization/charts.py)
           │                                   │
           ▼                                   ▼
[Backtest Execution Engine]             [Streamlit UI Terminal]
 (src/backtesting/engine.py)             ├── Market Analysis (Page 1)
 ├── Intra-bar Conservative Replay       ├── Quantitative Backtesting (Page 2)
 ├── Cost Model (Spread, Slippage, Comm) └── Business Intelligence (Page 3)
 └── Trade Ledger & Equity Curve
           │
           ▼
[Statistical & Robustness Suite]
 ├── Bootstrap 95% Confidence Intervals (Profit Factor)
 ├── Monte Carlo Equity Fan Chart (250 Resampled Paths)
 ├── Out-of-Sample Chronological Validation
 └── Vault Pre-Registration Gate (Holdout Testing)
```

---

## 2. Ingestion & Transformation Details

### A. Raw Feed Ingestion & Tick Aggregation
- **Binary Tick Archive (`.bi5`):** Raw Dukascopy binary files are decompressed and parsed using struct unpacking (`src/data/ingestion/bi5_decoder.py`). Price values are divided by calibrated instrument price factor ($1,000$ points/dollar for XAUUSD) to recover correct financial scale ($2,600$–$2,800$ USD/oz).
- **Bar Aggregation (`bar_builder.py`):** Discrete tick tuples `(timestamp_utc, ask, bid, volume)` are aggregated into standard OHLCV candlesticks for any target timeframe (M1, M5, M15, H1, H4).

### B. Quality Audit & Sanitization
- Every processed dataset is audited before consumption:
  1. No duplicate timestamp rows.
  2. Strict monotonicity ($t_{i+1} > t_i$).
  3. Strict candlestick geometric integrity ($H_i \ge \max(O_i, C_i)$ and $L_i \le \min(O_i, C_i)$).
  4. Non-negative volume and non-zero price spreads.
- An immutable audit trail is saved alongside the processed file: `reports/data_quality_{TF}_{timestamp}.json`.

### C. Analytical Isolation Principle
- When a user selects **SMC (Primary)**, the system feeds data exclusively through `src/smc/engine.py`.
- When a user selects **ICT (Secondary)**, the system feeds data exclusively through `src/ict/engine.py`.
- No analytical calculation crosses engine boundaries. Both engines output typed dataclass objects that adhere strictly to their respective theoretical rules.

### D. Execution Simulation & Cost Friction
- Strategies consume verified OHLC data alongside confirmed analytical events.
- To prevent look-ahead bias:
  - An event confirmed at bar $k$ becomes actionable only on or after bar $k+1$.
  - All orders are simulated tick-by-tick or intrabar-conservatively: if both Stop Loss and Take Profit fall within the high-low range of a single candle, the engine defaults to the conservative stop-loss assumption (`stop_first_on_collision`).
  - Transaction costs include dynamic/fallback bid-ask spread, adverse slippage per side, and lot commissions.

