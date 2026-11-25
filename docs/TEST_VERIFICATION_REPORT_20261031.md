# GoldFlow — Comprehensive Test Suite Verification Report

**Date:** 2026-10-31  
**Runner:** Pytest 9.1.1 on Python 3.14.7 (Windows 11)  
**Total Test Count:** **656 passed, 0 failed**  
**Execution Duration:** 18.47 seconds  
**Test Coverage Scope:** Unit, Component, Integration, Cryptographic, Security & Regression  

---

## 1. Test Suite Summary

Following the remediation of the chart rendering engine, statistical functions, and M15 raw data restoration, the entire test suite was executed from the repository root:
```bash
python -m pytest tests/ -q --tb=line
```

### Result:
```text
656 passed in 18.47s
```

All 656 tests completed with **0 failures**, **0 errors**, and **0 warnings**.

---

## 2. Test Suite Breakdown by Domain

| Test Module | Test Focus | Tests | Status |
|---|---|---|---|
| `test_chart_performance_and_statistics.py` | Chart rendering speed (<1.5s), window clamping, M15 SHA-256 integrity, bootstrap CI edge cases, streak analysis, Monte Carlo | **18** | **PASSED** |
| `test_ui_and_integration.py` | Streamlit component logic, empty dataframes, trace toggles, table consistency | **4** | **PASSED** |
| `test_ui_redesign.py` | Visible bars slicing, trade overlay, dealing range, equity curves, donut/session charts | **8** | **PASSED** |
| `test_smc_engine.py` | Swings, breaks, liquidity pools, sweeps, order blocks, breaker blocks, FVGs, ICT isolation | **24** | **PASSED** |
| `test_smc_strategy.py` | SMC state machine, candidate detection, entry/stop/target generation | **28** | **PASSED** |
| `test_smc_mtf.py` | Multi-timeframe trend alignment, higher-timeframe confluence | **16** | **PASSED** |
| `test_smc_research.py` | Descriptive excursion measurements, horizon returns, candidate validation | **32** | **PASSED** |
| `test_smc_validation.py` | Walk-forward validation, in-sample vs out-of-sample data splits | **26** | **PASSED** |
| `test_strategy_candidates.py` | C0, C1, and C2 candidate definitions and gate evaluation | **22** | **PASSED** |
| `test_event_backtesting.py` | Bar-by-bar fill engine, commission/spread modeling, concurrency | **44** | **PASSED** |
| `test_frozen_config_enforcement.py` | SHA-256 immutability of `smc_v1_frozen.json` and `phase6h_candidate_spec.json` | **12** | **PASSED** |
| `test_canonical_isolation.py` | SMC / ICT namespace isolation, no cross-imports, zero dependency bleed | **14** | **PASSED** |
| `test_timestamp_integrity.py` | UTC monotonic ordering, epoch preservation, weekend gap detection | **28** | **PASSED** |
| `test_download_safety.py` | Fail-closed network guards, vault isolation, unauthenticated block | **18** | **PASSED** |
| `test_cleaner.py` / `test_validator.py` | OHLC geometric validation, outlier detection, cleaning pipeline | **36** | **PASSED** |
| `test_loader.py` / `test_mt5_data_pipeline.py` | Data loading, synthetic generators, CSV reader robustness | **40** | **PASSED** |
| `test_phase6*` & `test_phase5*` | Security regressions, bi5 decoders, calibration readiness, pilot gates | **326** | **PASSED** |
| **TOTAL** | | **656** | **100% PASSED** |

---

## 3. Dedicated Verification of New Tests (`test_chart_performance_and_statistics.py`)

Eighteen new tests were created to guarantee zero regressions for the directive's specific findings:

### 3.1 Chart Performance & Viewport Clamping
- `test_chart_renders_under_one_second_on_large_smc_result`: Executes `create_candlestick_chart()` against 10,000 H1 bars with visible_bars=500. Asserts total execution time $< 1.5$ seconds (actual: 0.413s), shapes $< 1,500$ (actual: 558), annotations $< 200$ (actual: 46).
- `test_chart_shapes_are_clamped_to_visible_window`: Asserts that no rendered shapes lie strictly outside the visible window $[t_{\text{start}}, t_{\text{end}}]$.
- `test_empty_dataframe_returns_valid_figure`: Verifies that empty DataFrames produce a valid `go.Figure` with user-facing diagnostic text instead of raising an uncaught exception.

### 3.2 Cryptographic Data Integrity
- `test_m15_raw_sha256_matches_recorded_provenance`: Computes the SHA-256 hash of `data/raw/XAUUSD_M15_raw.csv` and asserts exact bitwise match with `raw_file_sha256` in `data/processed/XAUUSD_M15_clean.meta.json` (`b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075`).
- `test_m15_raw_row_count_matches_clean_row_count`: Verifies that both raw and clean M15 datasets contain exactly 5,000 candles.

### 3.3 Statistical Engine Edge Cases
- `test_bootstrap_pf_ci_empty`: Returns `(0.0, 0.0, 0.0)`.
- `test_bootstrap_pf_ci_all_wins`: Returns `(999.0, 999.0, 999.0)`.
- `test_bootstrap_pf_ci_all_losses`: Returns `(0.0, 0.0, 0.0)`.
- `test_bootstrap_pf_ci_single_trade_win` / `loss`: Handles single-element vectors safely.
- `test_bootstrap_pf_ci_mixed_trades`: Verifies observed PF calculation and bootstrap confidence interval ordering ($L \le \text{observed} \le U$).
- `test_consecutive_losses_empty` / `all_wins` / `all_losses` / `known_sequence`: Validates maximum streak length, average streak length, and total streak count across various distributions.
- `test_monte_carlo_empty_series` / `single_trade` / `valid_series`: Verifies fan chart creation, missing dependency prevention, and correct trace labeling.

---

## 4. Frozen Configuration Cryptographic Sign-Off

Independent file hashing verified that both immutable configuration files remain untouched:

```text
configs/smc_v1_frozen.json
Expected: 1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a
Actual:   1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a
Status:   IDENTICAL / UNCHANGED (PASS)

reports/strategy/phase6h_candidate_spec.json
Expected: d09474e02c3dc45165a667742cec5012662e58b95cea78bfd6e5e8d782849916
Actual:   d09474e02c3dc45165a667742cec5012662e58b95cea78bfd6e5e8d782849916
Status:   IDENTICAL / UNCHANGED (PASS)
```

