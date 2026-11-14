# GOLDFLOW — MASTER ARCHITECTURAL SPECIFICATION
## Quantitative Data Science, Institutional Market Structure & Backtesting Research Platform

**Status:** ACTIVE SPECIFICATION  
**Author:** Principal Software Architect & Quantitative Systems Lead  
**Canonical Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f` (sha1)  
**Primary Target Instrument:** `XAUUSD` (Spot Gold vs. US Dollar)  

---

## 1. System Mission & Core Philosophy

GoldFlow is a quantitative financial engineering workbench and institutional research platform engineered specifically for deep empirical study of gold market dynamics.

### Architectural Core Tenets:
1. **Primary Analytical Framework (Pure SMC):** Smart Money Concepts is the primary, default, standalone framework. It maintains its own deterministic structural rules (fractal swings, close-confirmed BOS/CHoCH, equal-high/low liquidity pools, wick-and-reclaim sweeps, break-confirmed Order Blocks, and swing dealing range / equilibrium).
2. **Secondary Analytical Framework (ICT):** Inner Circle Trader (ICT) is maintained as a completely independent, selectable engine in `src/ict/`. It maintains its own concepts (3-candle Fair Value Gaps, 50% Consequent Encroachment, displacement criteria, Market Structure Shifts, and BSL/SSL sweeps). SMC does not import or depend on ICT.
3. **Zero Look-Ahead Bias:** Every price structure, pivot, break, or order block records both its formation time and its exact confirmation time ($i + k$). Backtests and overlays only permit actions once confirmed.
4. **Zero-Trust Data Governance:** Real network ingestion gates are unconditionally fail-closed. Unverified broker price scales cannot authorize live network ingestion.
5. **Realistic Market Friction:** Event backtests model broker spreads, slippage, lot-sizing quantization, and commission models.

---

## 2. End-to-End System Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                GOLDFLOW UI LAYER                                        │
│  app.py ─── pages/1_Market_Analysis.py ─── pages/2_Backtesting.py ─── pages/3_BI_Dashboard │
└───────────────┬─────────────────────────────────┬─────────────────────────────────┬─────┘
                │                                 │                                 │
┌───────────────▼──────────────┐  ┌───────────────▼──────────────┐  ┌───────────────▼─────┐
│    DATA INGESTION & PIPELINE │  │   QUANTITATIVE ENGINES       │  │ EVENT-DRIVEN        │
│  - MT5 API Adapter           │  │  ┌────────────────────────┐  │  │ SIMULATOR & VAULT   │
│  - Dukascopy BI5 Decoder     │  │  │ PURE SMC ENGINE        │  │  │  - BacktestEngine   │
│  - BarBuilder (Tick -> M15)  │  │  │ (src/smc/)             │  │  │  - Cost Replay      │
│  - DataCleaner & Validator   │  │  └────────────────────────┘  │  │  - Evaluation Gates │
│  - PartitionStorageManager   │  │  ┌────────────────────────┐  │  │  - Holdout Vaults   │
│                              │  │  │ INDEPENDENT ICT ENGINE │  │  │  - Audit Ledger     │
│                              │  │  │ (src/ict/)             │  │  │                     │
│                              │  │  └────────────────────────┘  │  │                     │
└──────────────────────────────┘  └──────────────────────────────┘  └─────────────────────┘
```

---

## 3. Subsystem Breakdown

### 3.1 Data Ingestion & Quality Layer (`src/data/`, `src/data/ingestion/`)
- **`src/data/loader.py`:** MT5 terminal integration, historical bar retrieval, offline synthetic data generator.
- **`src/data/cleaner.py`:** OHLCV validation, bar chronological sorting, duplicate deduplication, spread anomaly detection, clean Parquet/CSV generation.
- **`src/data/validator.py`:** Mathematical invariants check (High $\ge$ Low, High $\ge$ Open/Close, Volume $\ge 0$).
- **`src/data/ingestion/bi5_decoder.py`:** Low-level big-endian LZMA binary tick parser (`>3I2f`).
- **`src/data/ingestion/dukascopy_provider.py`:** Provider-neutral Dukascopy Bank historical tick datafeed adapter with guarded bounded retrieval pilots.
- **`src/data/ingestion/instrument_spec.py`:** Instrument specifications, tick sizing, and unconditional fail-closed price scale gates (`validate_for_real_network_ingestion()`).

### 3.2 Primary Quantitative Engine: Smart Money Concepts (`src/smc/`, `src/strategy/`)
- **`src/smc/engine.py`:**
  - `analyze_smc(df, config: SMCConfig) -> SMCAnalysisResult`: Pure SMC pipeline.
  - Confirmed swings with configurable window ($k$).
  - Break of Structure (BOS) in trend continuation; Change of Character (CHoCH) on trend reversal.
  - Liquidity Pools: Equal highs/lows clustered within price tolerance (e.g. $\$0.50$).
  - Liquidity Sweeps: Wick penetration followed by candle close back inside the pool level.
  - Order Blocks: The origin candle prior to a confirmed BOS/CHoCH break.
  - Dealing Range: Lowest swing low to highest swing high, divided into Discount ($<50\%$) and Premium ($>50\%$).
- **`src/strategy/smc_setups.py`:**
  - Detection of the institutional setup hypothesis: **Sweep $\to$ CHoCH $\to$ OB Retest/Rejection**.
  - Directional filters and risk distance calculation.
- **`src/strategy/smc_research_candidates.py`:**
  - Standardized candidate specifications:
    - **C0 (Frozen SMC v1 Baseline):** Unfiltered full-session baseline.
    - **C1 (Session Filtered):** Restricts entries to London/NY killzones (Tested & Rejected in Phase 6G).
    - **C2 (Target Rationalized 2.0R):** Fixed 2.0R target replacing distant liquidity pools (Active research candidate).

### 3.3 Secondary Quantitative Engine: Inner Circle Trader (`src/ict/`)
- **`src/ict/engine.py`:** Unified ICT coordinator (`analyze_market_structure`).
- **`src/ict/fvg.py`:** 3-candle Fair Value Gap detection, Consequent Encroachment (50% midpoint), displacement detection via ATR multiplier and body/range ratio.
- **`src/ict/liquidity.py`:** Buy-side and sell-side liquidity sweeps and Market Structure Shifts (MSS).
- **`src/ict/order_blocks.py`:** Institutional displacement-origin Order Blocks with forward mitigation tracking.
- **`src/ict/structure.py`:** ICT structural break detection.

### 3.4 Event-Driven Backtesting & Simulation Engine (`src/backtesting/`)
- **`src/backtesting/engine.py`:**
  - High-fidelity sequential candle simulator.
  - Conservative intrabar resolution: Stop-loss executed first on collision bars.
  - Dynamic lot sizing based on realized equity and stop-loss distance.
  - Full transaction friction modeling: spread drag, slippage points, round-turn commission.

### 3.5 Institutional Vault & Governance Layer (`src/vault/`)
- **`src/vault/raw_storage.py`:** Partition storage manager, raw source persistence, SHA-256 manifests.
- **`src/vault/evaluation_gate.py`:** Forward evaluation registration, holdout isolation, single-pass validation gates.
- **`src/vault/audit_ledger.py`:** Append-only cryptographic audit ledger.

---

## 4. Framework Separation Guarantee

To prevent cross-framework contamination:
1. `src/smc/` modules **NEVER** import from `src/ict/`.
2. SMC data models (`SMCOrderBlock`, `SMCLiquidityPool`, `SMCStructureBreak`) are completely independent of ICT models (`OrderBlock`, `LiquiditySweep`, `FairValueGap`).
3. Streamlit UI pages (`pages/1_Market_Analysis.py`) provide explicit radio selectors separating SMC and ICT analysis modes.

