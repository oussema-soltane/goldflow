# GoldFlow Phase 3D.3.3 — M15 Integrity Recovery, Execution-Spec Validation, and Research Reproducibility Handoff

**Execution Date:** 2026-10-20  
**Phase Objective:** Recover M15 historical integrity with a verified 5,000-bar download, resolve test suite failures honestly without weakening readiness gates, enforce transactional fail-closed downloads, capture live MT5 execution specs and investigate the broker tick-value discrepancy, regenerate all Phase 3C research deliverables from genuine data, and enforce strict execution-spec backtest refusal.  
**Git Metadata:** No `.git` directory exists in this repository package; no commits or artificial Git hashes were assumed or generated.  
**Architecture Principle:** Pure SMC remains the primary framework. The independent ICT engine remains separate and functional. No strategy parameters were optimized or modified.

---

## 1. Repository and Inventory Status

- **Working Directory:** `GoldFlow_Phase3D3_2_CalcMode_Guard/GoldFlow_SMC_Primary_Updated`
- **Environment:** Windows 11, Python 3.13.7 (64-bit), MetaTrader 5 Build 6259 on `MetaQuotes-Demo` (Account #5057357767).
- **Inventory Audit:** Full inventory inspected across `src/`, `pages/`, `scripts/`, `tests/`, `reports/`, and `data/`.
  - Stale `.pyc` and pytest cache files were treated as transient artifacts, not authoritative sources.
  - Legacy partial M15 files quarantined to `data/quarantine/legacy_m15_quarantine/` prior to download promotion.

---

## 2. Root Cause and Disposition of the Failing Timestamp Test

### Root Cause
In `tests/test_timestamp_integrity.py::test_legacy_project_sidecars_are_explicitly_quarantined`, the test asserted that sidecars with `timestamp_mode_verified: false` must have `timestamp_integrity_status == "quarantined_legacy_data"`.  
However, the design introduced in Phase 3B/3D distinguishes three distinct integrity states:
1. `verified`: Feed has an explicit timestamp mode and operator/diagnostic verification (`timestamp_mode_verified: true`).
2. `normalized_by_explicit_mode`: Feed converted with explicit `server_wall_clock` or `posix_utc` mode, but unverified against live diagnostics. Must remain blocked by research gates.
3. `blocked_legacy_fixed_offset`: Legacy archive files converted using an obsolete, unrecoverable fixed 3-hour shift without DST awareness.

The test had an obsolete assertion conflating unverified data with legacy fixed-offset data, while the loader correctly sets `normalized_by_explicit_mode`.

### Disposition
Refactored `tests/test_timestamp_integrity.py` honestly to test and enforce all three states:
- `test_legacy_project_sidecars_are_explicitly_quarantined`: Verifies `normalized_by_explicit_mode` for unverified explicit-mode sidecars and `blocked_legacy_fixed_offset` for legacy files.
- `test_readiness_accepts_verified_timestamp_metadata`: Asserts readiness passes only when `timestamp_integrity_status == "verified"` and `timestamp_mode_verified is True`.
- `test_readiness_blocks_normalized_unverified_metadata`: Asserts readiness strictly blocks data with `normalized_by_explicit_mode`.
- Readiness requirements were **not weakened**.

---

## 3. MT5 Connectivity & Timestamp Diagnostic Output

Live read-only diagnostic was executed via `scripts/diagnose_mt5_timestamps.py --symbol XAUUSD --server-timezone Europe/Athens`:

- **Terminal:** MetaTrader 5 Build 6259 connected to `MetaQuotes-Demo`
- **Symbol:** `XAUUSD`
- **Machine UTC Reference:** `2026-10-20T13:32:26.761851+00:00`
- **Raw Tick Epoch:** `1792513946`
- **POSIX UTC Candidate:** `2026-10-20T16:32:26+00:00` (age: -10,799.2s, exactly 3 hours ahead of UTC)
- **Server Wall Clock Candidate:** `2026-10-20T13:32:26+00:00` (age: 0.8s relative to machine UTC)
- **Diagnostic Recommendation:** `server_wall_clock` (`candidate_matches_clock_within_tolerance`)
- **Process Exit Code:** `0`
- **Report Saved:** `reports/mt5_timestamp_diagnostic.json`

This conclusively re-proved that the connected broker feed encodes local Eastern European wall clock (`Europe/Athens`) into the integer epoch field.

---

## 4. M15 Downloaded Row Count and Verified UTC Coverage

Executed:
```bash
py -3.13 scripts/download_data.py --symbol XAUUSD --timeframes M15 --bars 5000 --timestamp-mode server_wall_clock --server-timezone Europe/Athens --confirm-timestamp-mode-verified
```

- **Candidate Download:** Staged transactionally in temporary files.
- **Pre-promotion Validation:** Zero invalid OHLC, zero duplicates, monotonic increasing UTC timestamps, zero future candles relative to retrieval date.
- **Downloaded Rows:** Exactly **5,000 completed bars** (replaces legacy 1,500-bar partial file).
- **UTC Date Range:** `2026-07-31 16:15:00+00:00` → `2026-10-20 13:30:00+00:00`
- **Retrieval Date:** `2026-10-20 13:56:43.421309+00:00` (terminal bar ended 26 minutes prior; forming active candle excluded).
- **Raw File SHA256:** `86074d0e40dc5cf9e784d04bdfc3e760bcc4e55256ba65596d27ccce39bdaa8d`
- **Integrity Status:** `timestamp_integrity_status = "verified"`, `timestamp_mode_verified = true`.
- **Diagnostic Trace:** Linked directly to `reports/mt5_timestamp_diagnostic.json`.

---

## 5. Provenance and Readiness Audit Across All Timeframes

Executed:
```bash
py -3.13 scripts/research_readiness.py
```
**Overall Status:** `READY_WITH_WARNINGS` (Exit code: `0`, zero critical blockers).

| Timeframe | Rows | Minimum Required | Provenance Status | Timestamp Mode | Server Timezone | Integrity Status | Date Range (UTC) | Blockers |
|---|---:|---:|---|---|---|---|---|---|
| **H4** | 5,000 | 2,000 | real_source_declared | `server_wall_clock` | `Europe/Athens` | verified | 2023-07-26 21:00 → 2026-10-19 13:00 | None |
| **H1** | 5,000 | 5,000 | real_source_declared | `server_wall_clock` | `Europe/Athens` | verified | 2025-12-05 04:00 → 2026-10-20 13:00 | None |
| **M15** | 5,000 | 5,000 | real_source_declared | `server_wall_clock` | `Europe/Athens` | verified | 2026-07-31 16:15 → 2026-10-20 13:30 | None |
| **M5** | 5,000 | 5,000 | real_source_declared | `server_wall_clock` | `Europe/Athens` | verified | 2026-09-22 23:15 → 2026-10-19 19:50 | None |

---

## 6. Execution-Spec Captures and Tick-Value Reconciliation

Executed:
```bash
py -3.13 scripts/capture_mt5_execution_specs.py --symbol XAUUSD
```
Captured specs directly from MT5 `symbol_info` and attached capture records to all 4 sidecars.

### Live MT5 API Inquiry
Conducted read-only calculation inquiry via `mt5.order_calc_profit` and `symbol_info`:
- `digits`: `2`
- `point`: `0.01`
- `trade_contract_size`: `100.0` (100 troy oz)
- `trade_tick_size`: `0.01`
- `trade_calc_mode`: `4` (`SYMBOL_CALC_MODE_CFDLEVERAGE`)
- `currency_base`: `XAU`, `currency_profit`: `USD`, `account_currency`: `USD`
- `trade_tick_value`: `0.1`
- `trade_tick_value_profit`: `0.1`
- `trade_tick_value_loss`: `0.1`

### Calculation Inquiry
- `mt5.order_calc_profit(ORDER_TYPE_BUY, "XAUUSD", 1.0, 4115.00, 4115.01)` = **1.00 USD**
- `mt5.order_calc_profit(ORDER_TYPE_BUY, "XAUUSD", 0.1, 4115.00, 4115.01)` = **0.10 USD**
- `mt5.order_calc_profit(ORDER_TYPE_BUY, "XAUUSD", 0.01, 4115.00, 4115.01)` = **0.01 USD**

### Reconciliation Finding
1. The linear contract size formula `(close - open) * contract_size * volume` evaluates to **$1.00** per $0.01 price move for a 1.0 lot trade.
2. The broker symbol property `trade_tick_value = 0.1` reported by `symbol_info` appears to represent tick value scaled to a **0.1 lot reference** or broker-side setting, rather than 1.0 lot.
3. As required by user instruction:
   - **Formulas and allowlists were NOT altered to force a pass.**
   - The execution specification audit remains strictly blocked on `TICK_VALUE_MISMATCH`.

---

## 7. Strict Execution-Specification Audit Status

Executed:
```bash
py -3.13 scripts/audit_execution_specs.py
```
- **Overall Status:** `TICK_VALUE_MISMATCH`
- **Exit Code:** `1`
- **Result:**
  - `H4`: `TICK_VALUE_MISMATCH` (tick value 0.1 vs expected 1.0)
  - `H1`: `TICK_VALUE_MISMATCH` (tick value 0.1 vs expected 1.0)
  - `M15`: `TICK_VALUE_MISMATCH` (tick value 0.1 vs expected 1.0)
  - `M5`: `TICK_VALUE_MISMATCH` (tick value 0.1 vs expected 1.0)

### Strict Backtest Enforcement
Executed:
```bash
py -3.13 scripts/run_smc_backtest.py --timeframes M5 --require-matched-execution-spec
```
- **Exit Code:** `1`
- **Message:** `BACKTEST NOT RUN: Execution specification gate blocked the backtest: status=TICK_VALUE_MISMATCH.`
- **Result:** Strict backtest refuses execution as designed. No uncalibrated P&L metrics were fabricated.

---

## 8. Full Test Suite, Compilation, and Audit Verification

All verification commands executed:

| Command | Exit Code | Result | Details |
|---|:---:|---|---|
| `py -3.13 -m compileall src pages scripts tests app.py -q` | **0** | PASSED | 0 syntax or compilation errors |
| `py -3.13 -m pytest tests/ -v` | **0** | PASSED | **350 passed**, 0 failed in 13.10s |
| `py -3.13 scripts/research_readiness.py` | **0** | PASSED | `READY_WITH_WARNINGS` |
| `py -3.13 scripts/audit_execution_specs.py` | **1** | BLOCKED | `TICK_VALUE_MISMATCH` (Strict gate working as intended) |
| `py -3.13 scripts/run_smc_backtest.py --timeframes M5 --require-matched-execution-spec` | **1** | BLOCKED | Refuses execution due to spec mismatch |

---

## 9. Regenerated Research Deliverables Registry

The Phase 3C SMC descriptive research pipeline was executed on the four genuine 5,000-bar datasets (`py -3.13 scripts/run_smc_research.py`):

- **Master Report:** `reports/PHASE3C_SMC_DESCRIPTIVE_RESEARCH.md`
- **JSON Dataset:** `reports/smc_descriptive_research.json`
- **Unified Setups CSV:** `reports/smc_setups_all.csv` (136 total setups: 68 Long / 68 Short)
- **Unified Excursions CSV:** `reports/smc_excursions.csv` (544 horizon evaluations)
- **Timeframe Events:**
  - `reports/smc_events_H4.csv` (2,655 events)
  - `reports/smc_events_H1.csv` (2,827 events)
  - `reports/smc_events_M15.csv` (3,042 events)
  - `reports/smc_events_M5.csv` (3,260 events)
- **Timeframe Setups:**
  - `reports/smc_setups_H4.csv` (15 setups: 8 Long / 7 Short)
  - `reports/smc_setups_H1.csv` (30 setups: 17 Long / 13 Short)
  - `reports/smc_setups_M15.csv` (49 setups: 21 Long / 28 Short)
  - `reports/smc_setups_M5.csv` (42 setups: 22 Long / 20 Short)
- **Common Overlapping Date Window:** `2026-09-22 23:15 UTC` → `2026-10-19 13:00 UTC` (M5: 42 setups, M15: 20 setups, H1: 1 setup, H4: 0 setups).
- **Superseded Reports Notice:** Prior Phase 3C reports that referenced the 1,500-bar partial M15 dataset are superseded by these regenerated artifacts.

---

## 10. Remaining Blockers and Next Steps

1. **Broker Tick-Value Clarification:**  
   The audit correctly blocks backtesting because `trade_tick_value` is `0.1` while contract size (100) × tick size (0.01) calculates to `1.0`. `order_calc_profit` produces $1.00 profit for 1.0 lot and $0.10 for 0.1 lot. To pass strict execution validation, an explicit decision is needed: either calibrate the audit rule for brokers reporting fractional-lot tick values (e.g. 0.1 lot reference) or confirm broker specifications.
2. **Backtesting Post-Spec Reconciliation:**  
   Once the tick value rule is formally aligned with broker conventions, rerun the strict event-driven backtesting pipeline across all timeframes.
3. **Independent ICT Benchmark:**  
   Keep ICT engine isolated as designed; after SMC backtesting is benchmarked, evaluate ICT comparative testing under identical execution parameters.
