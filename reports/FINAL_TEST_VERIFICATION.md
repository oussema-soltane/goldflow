# GOLDFLOW — FINAL TEST VERIFICATION REPORT

**Date:** 2026-11-11  
**Test Suite:** Pytest 9.1.1, Python 3.14.7  
**Operating System:** Windows 11  
**Command Executed:** `python -m pytest tests/ -q`  
**Execution Time:** 31.21 seconds  
**Total Tests:** **664 passed in full (100% pass rate)**  
**Failed:** 0 | **Errors:** 0 | **Skipped:** 0 | **XFailed:** 0

---

## 1. Test Suite Execution Summary

```
........................................................................ [ 10%]
........................................................................ [ 21%]
........................................................................ [ 32%]
........................................................................ [ 43%]
........................................................................ [ 54%]
........................................................................ [ 65%]
........................................................................ [ 75%]
........................................................................ [ 86%]
........................................................................ [ 97%]
................                                                         [100%]
664 passed in 31.21s
```

---

## 2. Test Module Breakdown

| Module | Test Count | Status | Description |
|---|---|---|---|
| `tests/test_canonical_isolation.py` | 6 | PASSED | Real data vs synthetic data strict directory isolation |
| `tests/test_capture_mt5_execution_specs.py` | 9 | PASSED | Terminal API execution spec capture and tick value reconciliation |
| `tests/test_chart_performance_and_statistics.py` | 18 | PASSED | Sub-second Plotly rendering (<0.5s), window clipping, shape count limits |
| `tests/test_cleaner.py` | 8 | PASSED | Data cleaner, missing value handling, OHLC coercion |
| `tests/test_download_safety.py` | 11 | PASSED | Downloader exit codes, transactional staging, fail-closed canonical overwrite guard |
| `tests/test_event_backtesting.py` | 40 | PASSED | Event-driven bar execution, next-bar open fill, stop-first resolution |
| `tests/test_execution_spec_audit.py` | 48 | PASSED | Contract size, tick size, volume step, CFD margin calculation rules |
| `tests/test_frozen_config_enforcement.py` | 9 | PASSED | Hash lock on `configs/smc_v1_frozen.json` (1091fb06...) |
| `tests/test_ict_adversarial.py` | 26 | PASSED | ICT edge cases: zero range bars, gap bars, weekend boundaries |
| `tests/test_ict_engine.py` | 4 | PASSED | ICT fractal swings, BOS, and CHoCH detection |
| `tests/test_ict_fvg.py` | 5 | PASSED | ICT fair value gaps and 50% consequent encroachment |
| `tests/test_ict_liquidity.py` | 3 | PASSED | ICT liquidity pools and wick sweeps |
| `tests/test_ict_order_blocks.py` | 4 | PASSED | ICT order blocks with displacement filters |
| `tests/test_ict_structure.py` | 5 | PASSED | ICT structure break logic |
| `tests/test_loader.py` | 8 | PASSED | MT5 historical bar ingestion and epoch conversion |
| `tests/test_mt5_data_pipeline.py` | 55 | PASSED | End-to-end MT5 pipeline, symbol discovery, error handling |
| `tests/test_phase41_cost_regression.py` | 24 | PASSED | Spread, slippage, commission replay cost consistency |
| `tests/test_phase4_validation.py` | 40 | PASSED | Phase 4 validation suite |
| `tests/test_phase5_regression.py` | 15 | PASSED | Phase 5 regression tests |
| `tests/test_phase6a1_security.py` | 12 | PASSED | Vault path traversal protection, permission boundaries |
| `tests/test_phase6a_ingestion.py` | 13 | PASSED | Multi-timeframe ingestion pipelines |
| `tests/test_phase6a_vault.py` | 5 | PASSED | Cryptographic vault registration and ledger integrity |
| `tests/test_phase6c_bi5_decoder.py` | 21 | PASSED | Dukascopy binary .bi5 tick decoding and candle synthesis |
| `tests/test_phase6d1_remediation.py` | 24 | PASSED | Phase 6D.1 remediation fixes |
| `tests/test_phase6d2_adversarial.py` | 18 | PASSED | Adversarial market data cases |
| `tests/test_phase6d_pilot.py` | 3 | PASSED | Pilot tests |
| `tests/test_phase6g_validation.py` | 18 | PASSED | Phase 6G statistical validation |
| `tests/test_phase6h_simulation_integrity.py` | 9 | PASSED | Fill realism, slippage, and stop/target conflict resolution |
| `tests/test_phase6i_calibration_readiness.py` | 13 | PASSED | Calibration readiness gates |
| `tests/test_research_framework.py` | 52 | PASSED | Descriptive research framework and statistical routines |
| `tests/test_smc_engine.py` | 22 | PASSED | Strict SMC engine causality, swings, BOS/CHoCH, OBs, FVGs, breakers |
| `tests/test_smc_mtf.py` | 10 | PASSED | Multi-timeframe SMC alignment without future look-ahead |
| `tests/test_smc_research.py` | 22 | PASSED | SMC statistical research calculations |
| `tests/test_smc_strategy.py` | 8 | PASSED | Sweep -> CHoCH -> OB Retest setup candidate generation |
| `tests/test_smc_validation.py` | 4 | PASSED | Strategy setup candidate validation |
| `tests/test_strategy_candidates.py` | 24 | PASSED | Strategy candidate evaluation routines |
| `tests/test_timestamp_integrity.py` | 16 | PASSED | Server wall clock, DST transitions, quarantine gates |
| `tests/test_ui_and_integration.py` | 4 | PASSED | Streamlit page integration and error resilience |
| `tests/test_ui_redesign.py` | 10 | PASSED | Chart presets, Y-axis autoscaling, and toggle controls |
| `tests/test_validator.py` | 14 | PASSED | Strict OHLC geometry and data quality validator |
| `tests/test_candidate_fixed_rr.py` | 4 | PASSED | **NEW:** 2R/3R partial-exit trade splitting and lot conservation |
| **TOTAL** | **664** | **100% PASSED** | |

---

## 3. Regression Safeguards Added This Turn

1. **`test_canonical_overwrite_guard_fails_closed_on_unreadable_file`** (`tests/test_download_safety.py`):
   Verifies that any file read or inspection error in the canonical overwrite guard strictly disallows overwriting and preserves original data.
2. **`test_canonical_overwrite_guard_blocks_shrinkage`** (`tests/test_download_safety.py`):
   Verifies that smaller live terminal fetches cannot replace larger canonical datasets.
3. **`test_candidate_trade_splits_into_two_legs`** (`tests/test_candidate_fixed_rr.py`):
   Verifies that when partial exits are configured, a trade correctly splits into Leg A (2R) and Leg B (3R) with exact lot conservation and zero lot leakage.
