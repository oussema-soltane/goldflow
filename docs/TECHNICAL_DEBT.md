# GOLDFLOW TECHNICAL DEBT & ARCHITECTURAL LOG

This document tracks known limitations, performance bottlenecks, technical debt, and planned architectural evolutions within the GoldFlow platform.

---

## 1. Resolved Technical Debt (Completed Milestones)

| Milestone | Component | Description of Resolution |
|---|---|---|
| **Phase 4** | SMC Engine Isolation | Decoupled SMC from ICT; established pure-SMC model structures without ICT imports. |
| **Phase 5** | Execution Realism | Introduced conservative `stop_first_on_collision` policy and granular transaction friction modeling. |
| **Phase 6A-6D** | Vault & Ingestion | Built cryptographic pre-registration gate (`src/vault/`) and historical tick ingestion architecture. |
| **Phase 6I** | Price Scale Calibration | Identified and calibrated Dukascopy price decoder scale ($1,000$ points/dollar) for XAUUSD. |
| **Master Directive P1.1** | SMC FVG Engine | Implemented independent pure 3-candle imbalance detection (`SMCFairValueGap`) with CE and lifecycle tracking. |
| **Master Directive P1.2** | Liquidity Pool Visuals | Upgraded liquidity pool chart overlays from thin lines to tolerance-band zone rectangles with hover diagnostics. |
| **Master Directive P2.2** | SMC Breaker Blocks | Implemented `detect_smc_breaker_blocks` tracking failed order block inversion into support/resistance and lifecycle retesting. |
| **Master Directive P1.3** | Statistical Robustness | Integrated non-parametric bootstrap 95% CI for Profit Factor and 250-path Monte Carlo equity fan charts in UI. |
| **Master Directive P2.1** | Candidate Gate UI | Embedded M15 Candidate Research (C0/C1/C2) comparative matrix and validation outcomes directly in `pages/2_Backtesting.py`. |

---

## 2. Active Technical Debt & Known Limitations

### TD-01: Historical Data Exhaustion on M15
- **Status:** Active / Governance Gate Closed.
- **Context:** All 5,509 available M15 bars (5,000 development + 509 validation) have been examined during Phases 4, 6F, and 6G.
- **Impact:** No eligible untouched in-sample or out-of-sample M15 data remains in the repository. Evaluating any new candidate on this dataset introduces retrospective selection bias.
- **Remediation Plan:** Historical ingestion must acquire and validate unexamined forward temporal periods (November 2026+) via `src/data/ingestion/` through the pre-registered vault protocol.

### TD-02: Microstructure Speed in Large-Scale Simulation
- **Status:** Moderate Priority.
- **Context:** Event-driven simulation over multi-year M1/M5 datasets executes in pure Python bar-by-bar loops.
- **Impact:** High-resolution backtests over $> 500,000$ candles can take several seconds to minutes.
- **Remediation Plan:** Vectorize candidate generation with Numba or Cython where possible, preserving the strict event-driven conservative collision semantics.

### TD-03: Multi-Timeframe Intraday State Synchronization
- **Status:** Low Priority / Exploratory.
- **Context:** Multi-timeframe trend alignment (`src/strategy/smc_mtf.py`) currently operates across H4 and H1 to guide M15/M5 execution. Lower timeframe bars (e.g., M1) do not yet dynamically stream into active higher timeframe candle aggregators in real-time.
- **Remediation Plan:** Build an asynchronous bar streaming buffer for live simulation replay.

