# GOLDFLOW CODEBASE INVENTORY

This document provides a comprehensive inventory of all source files in the GoldFlow quantitative research repository, detailing responsibilities, layer classification, core inputs, and key exports.

---

## 1. Core Analytical Engines

### Smart Money Concepts (SMC) — Primary Framework
| File | Layer | Description & Key Responsibilities | Dependents |
|---|---|---|---|
| `src/smc/models.py` | Domain Models | Pure-SMC data structures: `SMCSwingPoint`, `SMCStructureBreak`, `SMCLiquidityPool`, `SMCLiquiditySweep`, `SMCOrderBlock`, `SMCBreakerBlock`, `SMCFairValueGap`, `SMCAnalysisResult`. | `src/smc/engine.py`, `src/strategy/smc_setups.py`, `src/visualization/charts.py`, UI |
| `src/smc/engine.py` | Analytics Engine | Standalone deterministic SMC detection: swing pivots, close-confirmed breaks (BOS/CHoCH), equal high/low pools, wick-and-reclaim sweeps, order blocks, breaker blocks, 3-candle fair value gaps, dealing ranges. | `src/strategy/smc_setups.py`, `pages/1_Market_Analysis.py` |

### Inner Circle Trader (ICT) — Independent Secondary Framework
| File | Layer | Description & Key Responsibilities | Dependents |
|---|---|---|---|
| `src/ict/models.py` | Domain Models | ICT market structure data structures: `SwingPoint`, `StructureBreak`, `FairValueGap`, `LiquiditySweep`, `OrderBlock`, `DisplacementCandle`, `MarketStructureResult`. | `src/ict/engine.py`, `src/visualization/charts.py` |
| `src/ict/engine.py` | Analytics Engine | Orchestrator for independent ICT market analysis: calls structure, displacement, FVG, liquidity, and OB sub-modules. | `pages/1_Market_Analysis.py` |
| `src/ict/ict_structure.py` | Subsystem | Swing detection (fractal $k$-window) and BOS/CHoCH tracking based on close or wick rules. | `src/ict/engine.py` |
| `src/ict/ict_displacement.py` | Subsystem | ATR-based displacement candle identification. | `src/ict/engine.py` |
| `src/ict/ict_fvg.py` | Subsystem | ICT 3-candle Fair Value Gap detection requiring displacement confluence and consequent encroachment tracking. | `src/ict/engine.py` |
| `src/ict/ict_liquidity.py` | Subsystem | Sweep detection against prior swing highs and lows. | `src/ict/engine.py` |
| `src/ict/ict_order_blocks.py` | Subsystem | ICT order block identification requiring displacement and subsequent gap confirmation. | `src/ict/engine.py` |

---

## 2. Quantitative Strategy & Simulation

| File | Layer | Description & Key Responsibilities | Dependents |
|---|---|---|---|
| `src/strategy/smc_setups.py` | Signal Generation | State machine implementing the Sweep → CHoCH → Order Block Retest setup sequence. | Backtesting pipeline, UI |
| `src/strategy/smc_research_candidates.py` | Candidate Research | Implementation of C0 (Baseline), C1 (Session Filtered), and C2 (Target Rationalized) candidates with immutable specifications. | Candidate runners, UI |
| `src/strategy/smc_mtf.py` | Multi-Timeframe | Multi-timeframe trend timeline generator (`StructureTrendTimeline`) synchronizing H4 and H1 trend consensus. | MTF backtests |
| `src/backtesting/engine.py` | Execution Simulator | Event-driven bar-by-bar backtest engine with conservative intra-bar collision policy (`stop_first_on_collision`), tick-exact costs, and slippage. | `scripts/run_smc_backtest.py`, UI |
| `src/backtesting/cost_model.py` | Microstructure | Realistic broker friction model: contract sizing (100 oz/lot), point valuation, spread, adverse slippage, and commissions. | `src/backtesting/engine.py` |

---

## 3. Data Ingestion, Storage & Quality Assurance

| File | Layer | Description & Key Responsibilities | Dependents |
|---|---|---|---|
| `src/data/loader.py` | Data Access | Safe file loading, format detection, timezone validation, and metadata extraction for OHLCV data. | UI, scripts, clean pipeline |
| `src/data/cleaner.py` | Data Pipeline | Quality auditor: checks OHLC consistency, missing timestamps, duplicates, zero volume, and outputs validation reports. | `pages/1_Market_Analysis.py`, scripts |
| `src/data/ingestion/bi5_decoder.py` | Ingestion | Binary parser for Dukascopy `.bi5` compressed tick archives, with calibrated price scaling ($1000$ points/dollar for XAUUSD). | Data ingestion pipeline |
| `src/data/ingestion/bar_builder.py` | Ingestion | Tick-to-bar aggregator constructing regular M1, M5, M15, H1, H4 candles from discrete tick feeds. | Ingestion pipelines |
| `src/data/ingestion/validator.py` | Ingestion | Verification gate ensuring ingested feeds meet timestamp monotonicity, tick integrity, and price sanity standards. | Ingestion pipelines |
| `src/vault/evaluation_gate.py` | Governance | Cryptographic pre-registration and holdout gate enforcing zero look-ahead and unexamined evaluation protocols. | Research evaluation |
| `src/vault/holdout.py` | Governance | Cryptographic tamper-evident storage for chronological forward evaluation partitions. | Evaluation gate |

---

## 4. Visualization & Frontend (Streamlit)

| File | Layer | Description & Key Responsibilities | Dependents |
|---|---|---|---|
| `app.py` | Presentation | Application entry point and navigation hub for the GoldFlow terminal. | End users |
| `pages/1_Market_Analysis.py` | Presentation | Interactive visual workspace: Plotly chart rendering, SMC vs ICT framework switcher, structure summary tables. | End users |
| `pages/2_Backtesting.py` | Presentation | Quantitative strategy terminal: interactive backtest runner, statistical confidence panel (Bootstrap CI, Monte Carlo fan chart), candidate comparison gate (C0/C1/C2). | End users |
| `pages/3_BI_Dashboard.py` | Presentation | Institutional BI dashboard: multi-timeframe regime analysis, session heatmaps, volume profile, execution analytics. | End users |
| `src/visualization/charts.py` | Visualization | Decoupled Plotly charting library: dual-framework candlestick overlays, order blocks, breaker blocks, FVGs, liquidity pools, Monte Carlo fan charts, session bars. | All UI pages |

