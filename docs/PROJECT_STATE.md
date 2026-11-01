# GOLDFLOW — PROJECT STATE & REPOSITORY MEMORY
## Continuous Quantitative Engineering Handover & Subsystem Status Matrix

**Document Version:** 1.2.0  
**Last Updated:** November 1, 2026  
**Status:** ACTIVE  
**Primary Architect:** Principal Software Architect & Quantitative Systems Lead  

---

## 1. Canonical Project Baseline

| Parameter | Current Value / State |
| :--- | :--- |
| **Active Working Directory** | `c:\Users\ousse\Downloads\GoldFlow_Ultimate_Updated\GoldFlow_SMC_Primary_Updated` |
| **Canonical Git HEAD** | `1a529e2638832a4b6fcf88c388f68270fc6108a5` |
| **Git Object Format** | `sha1` |
| **Python Runtime** | Python 3.11+ x64 (Windows) |
| **Test Suite Baseline** | **656 passed**, 0 failed, 40 test suites |
| **Frozen SMC v1 Config Hash** | `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` (SHA-256) |
| **Frozen C2 Spec Hash** | `d09474e02c3dc45165a667742cec5012662e58b95cea78bfd6e5e8d782849916` (SHA-256) |
| **Network Ingestion Gate** | **FAIL-CLOSED** (`allow_network=False`, uncalibrated scale lock) |

---

## 2. Architectural Decisions Log (ADR)

### ADR-001: Primary Analytical Engine Dedicated to Pure SMC
- **Decision:** Smart Money Concepts (SMC) is established as GoldFlow's default, standalone primary analytical engine (`src/smc/`).
- **Rationale:** Institutional swing pivots, close-confirmed breaks of structure (BOS), changes of character (CHoCH), equal high/low liquidity pools, order blocks, breaker blocks, and 3-candle fair value gaps provide a mathematically deterministic baseline without heuristic ambiguity.
- **Status:** Implemented & Verified.

### ADR-002: Complete Architectural Decoupling of the ICT Engine
- **Decision:** Inner Circle Trader concepts are isolated inside `src/ict/`. SMC modules must never import from or reference ICT modules.
- **Rationale:** Prevents methodology bleed and cross-contamination. Fair Value Gaps (FVG), Consequent Encroachment (CE), displacement metrics, and Market Structure Shifts (MSS) remain cleanly testable as a standalone alternative.
- **Status:** Implemented & Verified (60+ ICT unit tests passing independently).

### ADR-003: Strict Elimination of Look-Ahead Bias via Pivot Delay
- **Decision:** Swing highs and lows require a $k$-bar confirmation window ($i + k$). No structure break or setup can be signaled before bar index $i + k$.
- **Rationale:** Prevents peeking into future price action during backtests and live telemetry.
- **Status:** Implemented & Verified.

### ADR-004: Fail-Closed Security & Instrument Price-Scale Gate
- **Decision:** Network data ingestion is disabled by default. Live XAUUSD ingestion is gated behind `validate_for_real_network_ingestion()`, which blocks until single-hour empirical reference calibration is executed.
- **Rationale:** Ensures raw tick binary formats (`.bi5`) do not corrupt accounts or backtests with 10x or 100x pricing miscalibrations.
- **Status:** Active & Locked.

### ADR-005: Rejection of Session Filter Candidate C1
- **Decision:** Phase 6G demonstrated that Candidate C1 (London/NY Killzones) overfit historical M5/M15 sample windows and failed to generalize on unseen validation data (PF collapsed from 1.257 to 0.699). C1 was officially rejected and must not be promoted.
- **Rationale:** Rigorous cost-adjusted backtesting showed a collapsed profit factor when transaction costs and out-of-sample periods were applied.
- **Status:** Formally Closed / Rejected.

### ADR-006: Target Rationalization Candidate C2 Retained for Research
- **Decision:** Candidate C2 (Fixed 2.0R / 3.0R Take-Profit) produced positive development (+282.81, PF 1.082) and validation (+265.02, PF 1.959) returns. It is retained as an active research candidate pending untouched M15 forward data acquisition.
- **Rationale:** Mitigates the structural flaw of waiting for distant, unmitigated opposing liquidity pools that rarely get reached before trailing reversals.
- **Status:** Active Research Track (Exploratory).

### ADR-007: High-Performance Chart Rendering & Data Integrity Remediation
- **Decision:** Resolved Plotly quadratic tuple concatenation ($O(K^2)$) by batching shapes and annotations in Python lists and passing them via bulk layout updates. Implemented visible-window temporal clamping $[t_{start}, t_{end}]$ to eliminate off-screen shape overload. Restored authentic 5,000-row `data/raw/XAUUSD_M15_raw.csv` with CRLF line endings, recovering exact 256-bit hash parity with `data/processed/XAUUSD_M15_clean.meta.json`. Centralized statistical functions with zero-division safety guards.
- **Rationale:** Prevents browser lockup and Streamlit rendering freezes while maintaining 100% full visual SMC fidelity and cryptographic provenance.
- **Status:** Implemented & Formally Verified (656 passing tests).

---

## 3. Subsystem Health Matrix

| Subsystem | Core Path | Status | Test Coverage | Key Capabilities / Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Data Ingestion** | `src/data/ingestion/` | Ready (Guarded) | High | Bi5 binary tick parser, Dukascopy adapter, fail-closed gate. |
| **Data Cleaning** | `src/data/cleaner.py` | Operational | Complete | OHLCV validation, duplicate removal, gap detection. |
| **SMC Engine** | `src/smc/` | Production | Complete | Swings, BOS, CHoCH, Liquidity Pools, Sweeps, OBs, Breaker Blocks, FVGs, Dealing Range. |
| **SMC Setups** | `src/strategy/smc_setups.py` | Production | Complete | Sweep $\to$ CHoCH $\to$ OB Retest state machine. |
| **ICT Engine** | `src/ict/` | Production | Complete | 3-bar FVGs, 50% CE, displacement filters, MSS, BSL/SSL sweeps. |
| **Backtester** | `src/backtesting/` | Production | Complete | Event-driven sequential candle execution, slippage, commission, conservative collision. |
| **Security Vault** | `src/vault/` | Operational | Complete | Holdout isolation, immutable registration hashes, audit logging. |
| **Visualization & UI** | `app.py`, `pages/` | Production | High | 3 Streamlit pages, dual-engine toggle, interactive Plotly charts, Monte Carlo fan charts, candidate gate UI. |

---

## 4. Completed Engineering Milestones This Session

1. **SMC Fair Value Gap Engine & UI (P1.1):**
   - Implemented `SMCFairValueGap`, `SMCFVGType`, `SMCFVGStatus` in `src/smc/models.py`.
   - Added `detect_smc_fvgs` in `src/smc/engine.py` (pure 3-candle imbalance without displacement requirement).
   - Rendered FVG zones with 50% CE midpoint and lifecycle dimming in `src/visualization/charts.py`.
   - Integrated sidebar parameter `smc_min_fvg_size`, overlay toggle `show_smc_fvgs`, and tabular summary in `pages/1_Market_Analysis.py`.

2. **SMC Liquidity Pool Zone Rectangles (P1.2):**
   - Upgraded liquidity pool overlays in `src/visualization/charts.py` from thin horizontal lines to tolerance-band rectangular zones with hover inspection and dimming for swept pools.

3. **SMC Breaker Block Engine (P2.2):**
   - Added `SMCBreakerBlock`, `SMCBreakerBlockType`, `SMCBreakerBlockStatus` in `src/smc/models.py`.
   - Added `detect_smc_breaker_blocks` in `src/smc/engine.py` detecting inverted failed OBs and tracking retest/invalidation lifecycle.
   - Comprehensive unit test suite in `tests/test_smc_engine.py` (21 passing unit tests).

4. **Statistical Context & Non-Parametric Robustness (P1.3):**
   - Integrated sample size adequacy warning ($N < 30$ underpowered flag).
   - Implemented 1,000-resample non-parametric bootstrap 95% Confidence Interval for Profit Factor.
   - Built 250-path Monte Carlo equity fan chart (`create_monte_carlo_equity_fan_chart`) with 10th, 50th, 90th percentile bands and realized trajectory.
   - Analyzed consecutive loss streaks in `pages/2_Backtesting.py`.

5. **M15 Candidate Research Gate in UI (P2.1):**
   - Added new Tab 2 in `pages/2_Backtesting.py` presenting C0 (Frozen Baseline), C1 (Session Filter), and C2 (Target Rationalized).
   - Embedded development vs. validation performance matrix and formal gate decisions (C1 rejected, C2 exploratory).

6. **Documentation Suite (P3):**
   - Created `docs/CODEBASE_INVENTORY.md` mapping all 45 source files.
   - Created `docs/DATA_FLOW.md` documenting end-to-end data lifecycle.
   - Created `docs/TECHNICAL_DEBT.md` cataloging known limitations and remediation tracks.

---

## 5. Next Concrete Priorities

1. **Forward Temporal Data Ingestion Staging (P2):**
   - Prepare cold-storage ingestion staging for unexamined forward XAUUSD M15 periods (November 2026+) via the pre-registered vault protocol (`src/vault/evaluation_gate.py`) to evaluate Candidate C2 without selection bias.
2. **Authorized Price-Scale Reference Calibration (P2):**
   - Execute single-hour reference calibration against authoritative quote (`$4,156.94` at `2026-10-15 10:00 UTC`) when user grants network permissions.
3. **Simulation Acceleration (P3):**
   - Profile high-resolution M1/M5 simulation pipelines for vectorization opportunities.
