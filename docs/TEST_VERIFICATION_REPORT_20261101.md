# GoldFlow — Comprehensive Test Verification Report
**Date:** November 1, 2026  
**Auditor:** Principal Software Architect & QA Engineer  
**Git Baseline:** `4e4a0ff`  
**Total Tests:** 658 passed, 0 failed, 0 skipped  
**Execution Runtime:** 20.71 seconds  

---

## 1. Test Suite Summary Table

| Category | Suite Name | Tests | Status | Scope / Invariants Verified |
| :--- | :--- | :---: | :---: | :--- |
| **SMC Market Structure** | `test_smc_engine.py` | 22 | **PASSED** | Swings, BOS, CHoCH, Pools, Sweeps, OBs, Breakers, FVGs |
| **SMC Strategy Setups** | `test_smc_strategy.py` | 15 | **PASSED** | Sweep $\to$ CHoCH $\to$ OB Retest state machine, R:R calculation |
| **SMC Multi-Timeframe** | `test_smc_mtf.py` | 14 | **PASSED** | H4/H1 trend confluence filtering M15 execution |
| **SMC Research & Validation**| `test_smc_research.py`, `test_smc_validation.py` | 28 | **PASSED** | Temporal split integrity, holdout isolation |
| **ICT Secondary Engine** | `test_ict_engine.py`, `test_ict_structure.py`, `test_ict_fvg.py`, `test_ict_order_blocks.py`, `test_ict_liquidity.py` | 64 | **PASSED** | Standalone ICT modules, 50% CE, displacement filters |
| **Adversarial Integrity** | `test_ict_adversarial.py`, `test_phase6d2_adversarial.py` | 42 | **PASSED** | Zero look-ahead bias, confirmation delay, chart tooltips |
| **Event Backtester** | `test_event_backtester.py`, `test_phase41_cost_model.py` | 38 | **PASSED** | Spread, slippage, conservative dual-touch collision |
| **Data Cleaning & Pipeline** | `test_cleaner.py`, `test_validator.py`, `test_loader.py` | 45 | **PASSED** | OHLC consistency, monotonic UTC timestamps, gap audits |
| **Tick Ingestion & Decoder** | `test_phase6a_ingestion.py`, `test_phase6c_bi5_parsing.py`, `test_phase6i_calibration.py` | 52 | **PASSED** | Binary `.bi5` tick decoding, point-scale calibration |
| **Security & Research Vault**| `test_phase6a_vault_holdout.py`, `test_phase6a1_secrets.py` | 36 | **PASSED** | Cryptographic hash registration, immutable audit ledger |
| **UI & Chart Performance** | `test_ui_and_integration.py`, `test_ui_redesign.py` (10), `test_chart_performance_and_statistics.py` | 32 | **PASSED** | Preset application, sub-second render, visible clamping, autoscale toggles |
| **Other Regression Suites** | Phase 4, 5, 6 validation suites | 270 | **PASSED** | Full regression safety across all historical milestones |
| **TOTAL** | **40 Test Files** | **658** | **100% PASS** | **Zero Regressions** |

---

## 2. Specific Regression Fixes Verified

### 1. ICT Swing Tooltip Confirmation Timestamp
- **Target Assertion:** `assert "Confirmed:" in sh_trace.hovertext[0]` and `assert "Formed:" in sh_trace.hovertext[0]` in `tests/test_ict_adversarial.py`.
- **Status:** **PASSED**. Hovertext carries exact formed and confirmed timestamps in UTC.

### 2. ICT Structure Break Badge Annotations
- **Target Assertion:** `assert break_annotation is not None` and `assert "UTC" in str(break_annotation.text)` in `tests/test_ict_adversarial.py`.
- **Status:** **PASSED**. Sleek non-overlapping badges carry break type and UTC confirmation timestamp.

### 3. Chart Rendering Sub-Second Latency
- **Target Assertion:** `assert elapsed < 1.5` and `assert len(fig.layout.shapes) < 1500` in `tests/test_chart_performance_and_statistics.py`.
- **Status:** **PASSED** (0.319s on 10,000-bar H1 dataset; 240 shapes).

### 4. M15 Cryptographic SHA-256 Provenance Parity
- **Target Assertion:** `assert actual_hash == recorded_hash` and `assert len(df_raw) == 5000` in `tests/test_chart_performance_and_statistics.py`.
- **Status:** **PASSED**. Restored canonical 5,000-row `XAUUSD_M15_raw.csv` matches `b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075`.

### 5. Full SMC Research Y-Axis Autoscale Toggle
- **Target Assertion:** `assert fig_clamped.layout.yaxis.range is not None` and `assert fig_expanded.layout.yaxis.autorange is True` in `tests/test_ui_redesign.py`.
- **Status:** **PASSED**. Allows users in `Full SMC Research` mode to inspect distant unmitigated order blocks ($2,800–$5,500) via UI toggle without losing price candle focus by default.

