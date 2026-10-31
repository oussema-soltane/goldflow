# GoldFlow Phase 6B: External Market-Data Provider Requirements Specification

**Author:** Senior Quantitative Research Engineer & Financial Data Architect  
**Date:** 2026-10-28  
**Status:** Canonical Requirements Specification  
**Primary Instrument:** XAUUSD (Gold Spot Bullion vs. US Dollar)  
**Primary Strategy:** Frozen SMC v1 (`configs/smc_v1_frozen.json`, SHA-256: `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`)  
**Secondary Engine:** Independent ICT Engine (Canonical Isolation Verified)  

---

## 1. Executive Summary & Research Baseline

This document specifies the technical, quantitative, operational, and legal data requirements for GoldFlow's Phase 6 external market-data integration. GoldFlow requires high-fidelity market data to fulfill two independent research workflows:
1. **Cross-Provider Generalization & Robustness Testing:** Evaluating whether institutional Smart Money Concepts (SMC) order-block and liquidity setups generalize across different venue matching engines, or whether performance is an artifact of specific broker spread markups and synthetic quote feeds.
2. **Forward Temporal Evaluation (Out-of-Sample Holdout):** Evaluating frozen strategy rules against newly observed, unadulterated market data collected strictly after pre-registration ($T_{\text{obs}} \ge T_{\text{reg}} \land T_{\text{ingest}} \ge T_{\text{reg}}$) in an isolated, tamper-evident holdout vault.

### 1.1 Project Baseline & Commit Integrity
Prior to establishing data requirements, the repository baseline was verified directly via Git tooling:
- **Canonical Git HEAD Revision:** `ad9807f8405811d65148d73d72139243f3d6a77f` (abbreviated `ad9807f`).
- **Object Format:** `sha1` (standard 40-character hexadecimal digest, verified `[0-9a-f]`).
- **Working-Tree Status:** In-tree development (17 modified tracked files, untracked research directories `src/data/ingestion/`, `src/vault/`, `reports/phase5/`, `reports/phase6/`).
- **Frozen Strategy Configuration:** `configs/smc_v1_frozen.json` verified with SHA-256:
  `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` (100% byte-exact preservation).
- **Core Architecture Invariants:** Complete isolation between SMC and ICT engines (zero cross-imports), strict read-only evaluation gating, and zero live-trading code.

---

## 2. Requirements Classification Matrix

Requirements are strictly partitioned into **Must-Have (Required for Viability)** and **Nice-to-Have (Desirable / Optimizations)**. Any provider candidate that fails a single Must-Have requirement cannot be selected as the primary provider for that workflow.

| ID | Dimension | Research Requirement | Classification | Justification |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-01** | Instrument Availability | Spot Gold vs. US Dollar (`XAUUSD`) | **MUST-HAVE** | Core research instrument. Futures (COMEX `GC`) or synthetic CFDs are non-fungible with spot cash flows. |
| **REQ-02** | Bid / Ask Quote Streams | Independent Top-of-Book Bid & Ask | **MUST-HAVE** | Spread ($S = P_{\text{ask}} - P_{\text{bid}}$) dynamic modeling, slippage simulation, and exact directional entry/exit execution. |
| **REQ-03** | Sub-Second Timestamp Precision | Millisecond or Microsecond in UTC | **MUST-HAVE** | Intraday bar construction (M1), microsecond collision sequencing, and temporal boundary enforcement. |
| **REQ-04** | Dual-Timestamp Support | Explicit Observation vs Ingestion Time | **MUST-HAVE** | Eliminates historical backfill leakage into forward holdout partitions ($T_{\text{obs}} \ge T_{\text{reg}} \land T_{\text{ingest}} \ge T_{\text{reg}}$). |
| **REQ-05** | Forward Continuous Collection | Real-time streaming (WebSocket, FIX, polling) | **MUST-HAVE** | Required to collect out-of-sample forward observations into `goldflow_vault/raw_vault/` post-registration. |
| **REQ-06** | Historical Tick Archive | Multi-month/multi-year historical tick files | **MUST-HAVE** (Cross-Eval) | Required for cross-provider feed reconciliation and multi-year backtesting across market regimes. |
| **REQ-07** | Non-Commercial / Research Rights | Permitted for quantitative backtesting & model R&D | **MUST-HAVE** | Legal compliance with data licensing agreements; derived bar storage must be authorized. |
| **REQ-08** | Zero Upfront Capital Outlay | Evaluation possible without mandatory paid commitment | **MUST-HAVE** (Due Diligence) | Phase 6 research mandate: no purchases, no funded account deposits, no ongoing API subscription charges. |
| **REQ-09** | Sequence Identifiers | Monotonic packet/tick sequence IDs | **DESIRABLE** | Facilitates sequence-aware deduplication and microsecond order preservation without timestamp clashing. |
| **REQ-10** | Level 2 / Market Depth | BBO + Order Book Depth (L2/L3) | **DESIRABLE** | Enables order book imbalance analysis and institutional liquidity sweep modeling. |
| **REQ-11** | Public API SDK / Protocols | Standard Python SDK, REST, or WebSocket | **DESIRABLE** | Minimizes adapter complexity and eliminates native C++/.NET binary wrapper dependencies. |
| **REQ-12** | Deterministic Missing-Data Codes | Explicit venue closure / holiday gap signaling | **DESIRABLE** | Prevents synthetic quote generation across weekend closures and bank rollover periods. |

---

## 3. Deep-Dive Assessment Across 15 Core Workload Dimensions

### 3.1 Dimension 1 — XAUUSD Instrument Availability & Exact Symbol Definition
- **Requirement:** Physical spot gold bullion denominated in USD (1 troy ounce = 31.1034768 grams).
- **Critical Context:** Many retail brokers offer synthetic OTC CFDs (`XAUUSD.a`, `GOLD_spot`) with proprietary financing charges, artificial spread markups, and arbitrary holiday calendars. Institutional venues quote spot gold (`XAU/USD`) against Loco London bullion delivery standards (unallocated gold cleared via London Precious Metals Clearing Limited - LPMCL).
- **Symbol Variations Across Candidates:**
  - Dukascopy: `XAU/USD` (Commodity CFD based on SWFX spot marketplace).
  - LMAX Global: `XAU/USD` (Spot CFD or spot bullion under broker terms).
  - LMAX Exchange: `XAU/USD` (Physical spot bullion, London Loco settlement, CLOB).
  - Interactive Brokers: `XAUUSD` (Spot Gold via IdealPro for non-US clients; COMEX `GC` futures or Paxos unallocated gold for US clients).
  - TrueFX: **NOT SUPPORTED**. Public archives and streaming APIs cover fiat currencies only (`EUR/USD`, `GBP/USD`, etc.).

### 3.2 Dimension 2 — Historical Tick Availability
- **Requirement:** True tick-level quotes representing genuine quote updates from liquidity providers, rather than artificially resampled bars.
- **Quantitative Necessity:** SMC strategy signals on lower timeframes (M1, M15) depend on precise high/low extremes formed during liquidity sweeps. Interpolated or downsampled ticks compress wick extremes, leading to false order block mitigations and inaccurate backtest executions.

### 3.3 Dimension 3 — Historical Bid/Ask Quote Availability
- **Requirement:** Concurrently recorded Bid and Ask prices for every tick observation.
- **Spread Dynamic Analysis:** Gold spreads widen dramatically during:
  - Daily rollover (21:00–22:00 UTC): from typical 15–25¢ to 100–300¢ (\$1.00–\$3.00/oz).
  - High-impact macroeconomic releases (US CPI, NFP, FOMC): rapid spread blowout.
  - Feeds providing only "mid" or "last traded" price conceal spread risk, resulting in over-optimistic fill assumptions.

### 3.4 Dimension 4 — Forward Continuous Collection Post-Registration
- **Requirement:** Capability to stream or periodically poll live quotes continuously after an evaluation registration timestamp $T_{\text{reg}}$.
- **Integration Constraint:** Ingestion pipeline must record $T_{\text{ingest}}$ immediately upon packet arrival at the local network interface, binding it cryptographically to the raw observation.

### 3.5 Dimension 5 — Source Timestamp Precision & Timezone Semantics
- **Requirement:** Standardized UTC timezone awareness with millisecond ($10^{-3}$s) or microsecond ($10^{-6}$s) resolution.
- **Protocol Hazard:** Timestamps expressed in local broker time (e.g. MetaTrader server time UTC+2 / UTC+3 with daylight saving transitions) introduce temporal alignment errors, misaligning London and New York session killzones.

### 3.6 Dimension 6 — Sequence Numbers & Event Identifiers
- **Requirement:** Monotonic integer sequence identifiers assigned by the matching engine or data publisher.
- **Deduplication Role:** GoldFlow's sequence-aware validator ([validator.py](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/src/data/ingestion/validator.py)) distinguishes between legitimate microsecond collisions (two quotes occurring within the same millisecond having different sequence IDs) and true network packet duplicates (identical timestamp, prices, and sequence ID).

### 3.7 Dimension 7 — Historical Coverage & Download Granularity
- **Requirement:** Minimum 3–5 years of continuous historical tick data partitioned into manageable hourly or daily files.
- **Storage Profile:** XAUUSD generates approximately 20,000 to 80,000 ticks per active trading day (~15 to 25 million ticks per year). Data must be retrievable in modular partitions (e.g., hourly LZMA `.bi5` or daily compressed Parquet) to prevent HTTP connection timeouts and memory overflow.

### 3.8 Dimension 8 — Missing-Data Behavior & Retrieval Completeness
- **Requirement:** Deterministic signaling of market closure periods.
- **Schedule Definition:** Spot gold trading commences Sunday at 22:00 or 23:00 UTC and closes Friday at 21:00 or 22:00 UTC, with a daily mandatory maintenance halt between 21:00 and 22:00 UTC. The ingestion adapter must verify that missing data during closure periods is recognized as normal market cessation rather than network packet drop.

### 3.9 Dimension 9 — API Access & Request-Pacing Limitations
- **Requirement:** Well-documented rate limits and non-punitive throttling behavior.
- **Vulnerability Audit:** APIs enforcing aggressive burst limits (e.g., Interactive Brokers' 60 historical requests per 10 minutes, with bid/ask requests counting double) can throttle bulk historical extraction scripts for hours or trigger IP bans. Providers offering flat-file CDN downloads or generous streaming quotas are heavily preferred for high-throughput quantitative pipelines.

### 3.10 Dimension 10 — Authentication & Credential Management
- **Requirement:** Decoupled credential management via environment variables (`.env`) or local session tokens.
- **Security Invariant:** Zero credentials stored in source files, git commits, or public logs. Ingestion must fail gracefully with `AuthenticationError` if required tokens are absent, without halting independent repository tests.

### 3.11 Dimension 11 — Pricing, Subscriptions & Minimum Account Requirements
- **Requirement:** Feasibility of comprehensive technical evaluation without financial commitment.
- **Evaluation Rule:** Due diligence mandates zero expenditure on market data subscriptions or live account deposits during the feasibility phase.

### 3.12 Dimension 12 — Permitted Research Use & Data-Retention Rights
- **Requirement:** Explicit contractual permission to store data locally for quantitative research, backtesting, and academic evaluation.
- **Legal Distinction:** Most providers permit internal quantitative research while strictly prohibiting commercial redistribution of raw tick streams. Storing derived analytical artifacts (such as aggregated OHLC bars and backtest trade logs) is universally permitted under fair-use research clauses.

### 3.13 Dimension 13 — Retention of Derived OHLC Bars
- **Requirement:** Authority to transform raw tick streams into canonical M1, M15, H1, and H4 Parquet datasets and retain them indefinitely in `goldflow_vault/derived/`.
- **Finding:** Derivation of compressed, downsampled OHLC bars constitutes a transformative analytical work, fully permitted under standard market data licensing terms across all examined institutions.

### 3.14 Dimension 14 — Feed Differences: Institutional ECN vs. Retail MT5 Data
- **MT5 Broker Feed Properties:**
  - Retail broker B-book or LP aggregation with fixed or widened spread markup (+10¢ to +30¢ per ounce).
  - Synthetic filtering: retail broker bridges frequently suppress microsecond quote flurries to conserve bandwidth.
  - Server time offset: typically UTC+2 / UTC+3 (Eastern European Time) with Daylight Saving Time shifts.
- **Institutional ECN / Interbank Properties:**
  - Raw Central Limit Order Book or interbank aggregation with raw spreads (often 10¢ to 18¢ during London/NY overlap).
  - Microsecond burst volatility: genuine liquidity sweeps and instantaneous price discoveries.
  - Strict UTC timestamping directly from matching engine clocks.
- **Implication for SMC Strategy:** SMC setups (Fair Value Gaps, Liquidity Sweeps, Order Blocks) identified on MT5 data must be reconciled against institutional feeds to test whether key liquidity levels match institutional pricing or are distorted by retail broker pricing engines.

### 3.15 Dimension 15 — Integration Complexity with `DataIngestionProvider`
- **Requirement:** Seamless compatibility with GoldFlow's existing provider-neutral interface:
  - `fetch_historical_ticks(symbol, start_time, end_time) -> Tuple[List[RawTickObservation], Dict]`
  - `stream_incremental_ticks(symbol, max_ticks) -> Iterator[RawTickObservation]`
  - `get_instrument_specification(symbol) -> Dict[str, Any]`
- **Design Assessment:** Providers offering clear REST/HTTP endpoints or simple binary file structures can be wrapped in 150–300 lines of standard Python, whereas providers requiring local binary gateway daemons (e.g. IB Gateway) or institutional FIX protocol engines require complex multi-threaded socket management and state machines.

---

## 4. Summary of Workload Fit

| Evaluation Component | GoldFlow Target Requirement |
| :--- | :--- |
| **Asset Class** | Precious Metals — Spot Bullion (`XAUUSD`) |
| **Price Channels** | Concurrently observed Top-of-Book Bid & Ask |
| **Historical Depth** | $\ge 3$ years of tick-by-tick records |
| **Forward Collection** | Real-time streaming or automated hourly polling |
| **Target Storage** | Snappy-compressed Parquet with SHA-256 manifest chaining |
| **Derived Timeframes** | M1 canonical bars $\to$ Resampled M15, H1, H4, D1 |
| **Cost Profile** | Zero initial purchase cost for research feasibility |

