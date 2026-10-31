# PHASE 6H — Data Inventory and Evaluation Readiness Report
## Dataset Accounting, Holdout Expiry, and Phase 6E External Data Prerequisites

**Repository Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Frozen SMC v1 Config Hash:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`  
**Date:** 2026-10-30 | **Status:** READINESS AUDIT COMPLETE — EVALUATION PENDING DATA  

---

## 1. Executive Summary

A comprehensive inventory of all datasets in `data/processed/` and `data/raw/` was conducted to determine what market data remains eligible for an independent evaluation of candidate C2 (`SMC_v2_target_rationalized`).

**Critical Finding:**  
**Zero eligible, untouched M15 data remains in the workspace.**  
All 5,509 available M15 bars (spanning 2026-08-04 to 2026-10-29 UTC) have now been examined:
- The first 5,000 bars (`data/processed/XAUUSD_M15_clean.csv`) were used for Phase 6F candidate discovery.
- The remaining 509 bars (`data/processed/XAUUSD_M15_validation_window.csv`) were used in Phase 6G to validate C1 and inspect C2.

Re-evaluating C2 on any part of these 5,509 bars would constitute circular confirmation. A genuinely independent evaluation requires newly ingested external market data. In strict accordance with project rules, the fail-closed network gate remains closed until explicit operator authorization and price-scale validation are granted under Phase 6E protocols.

---

## 2. Exhaustive Dataset Accounting & Classification

| File Path | Timeframe | Bar Count | Start Date (UTC) | End Date (UTC) | SHA-256 (First 16 chars) | Research Classification |
|---|---|---|---|---|---|---|
| `data/processed/XAUUSD_M5_clean.csv` | M5 | 99,999 | 2025-05-13 22:15 | 2026-10-20 15:50 | `76d3d4fc95069694…` | **EXAMINED DEVELOPMENT** (M5 candidate discovery) |
| `data/processed/XAUUSD_M15_clean.csv` | M15 | 5,000 | 2026-08-04 12:00 | 2026-10-22 09:15 | `2f6bded7fc58752a…` | **EXAMINED DEVELOPMENT** (Phase 6F candidate selection) |
| `data/processed/XAUUSD_H1_clean.csv` | H1 | 10,000 | 2025-01-31 14:00 | 2026-10-20 14:00 | `2192f4c1f22010a7…` | **EXAMINED DEVELOPMENT** (HTF context in Phase 3E/6F) |
| `data/processed/XAUUSD_H4_clean.csv` | H4 | 5,000 | 2023-07-27 17:00 | 2026-10-20 09:00 | `3a5f3342899e7539…` | **EXAMINED DEVELOPMENT** (HTF context in Phase 3E/6F) |
| `data/processed/XAUUSD_M15_validation_window.csv` | M15 | 509 | 2026-10-22 09:30 | 2026-10-29 22:30 | `794f095a82a58220…` | **EXAMINED VALIDATION** (Phase 6G validation segment) |
| `data/raw/XAUUSD_M15_raw.csv` | M15 | 1,500 | 2026-10-07 03:45 | 2026-10-29 22:30 | `bd347dc95f84a786…` | **EXAMINED** (991 bars overlap clean; 509 bars in val) |
| `data/raw/XAUUSD_M5_raw.csv` | M5 | 99,999 | 2025-05-13 22:15 | 2026-10-20 15:50 | `7c5c5187bbb65933…` | **EXAMINED** (Source for clean M5) |
| `data/raw/XAUUSD_H1_raw.csv` | H1 | 10,000 | 2025-01-31 14:00 | 2026-10-20 14:00 | `ed050b1b273d0801…` | **EXAMINED** (Source for clean H1) |
| `data/raw/XAUUSD_H4_raw.csv` | H4 | 5,000 | 2023-07-27 17:00 | 2026-10-20 09:00 | `9bf68ed4b607aa91…` | **EXAMINED** (Source for clean H4) |

---

## 3. Data Integrity & Ingestion Boundary Invariants

1. **No Synthetic Market Data:** Synthetic data generation is strictly restricted to unit tests (`tests/fixtures/`) and is forbidden for strategy evaluation or validation.
2. **Fail-Closed Network Gate Active:**
   - No external requests to Dukascopy, Interactive Brokers, or MT5 live terminals were executed.
   - The price-scale gate in `src/data/ingestion/dukascopy/decoder.py` remains active.
3. **Phase 6E Ingestion Prerequisites:**
   - Before downloading any new XAUUSD data, the operator must explicitly authorize network ingestion.
   - Price scale verification must confirm that raw BI5 quote decimals decode to standard USD spot gold scale ($4,000+ range) without truncation or scaling distortion.

---

## 4. Chronological Evaluation Protocol for Candidate C2

When new, authenticated XAUUSD data becomes available, the evaluation must execute strictly under the following protocol:

### 4.1 Frozen Candidates Under Comparison
- **Control Benchmark:** `SMC_v1_frozen_baseline` (C0, version 1.0.0).
- **Primary Research Candidate:** `SMC_v2_target_rationalized` (C2, version 2.0.0-alpha.2).
- **Discarded / Inconclusive:** `SMC_v2_session_filtered` (C1) remains archived as not promoted.

### 4.2 Invariant Account & Execution Configuration
Both candidates must run on the exact same date window with identical parameters:
- Starting capital: **$10,000.00 USD**.
- Risk fraction: **1.0%** per trade ($100 risk on initial capital).
- Execution costs: **$0.20 spread per side, $0.05 slippage per side, $0.00 commission**.
- Contract size: **100 oz** per standard lot ($1.00 move = $100 per lot).
- Max concurrent positions: **1** (single-shot execution queue).
- Collision resolution: **`conservative_stop_first = True`**.

### 4.3 Mandatory Reporting Schema
- Realized Trade Ledger (`.csv`) containing `raw_gross_pnl`, `total_transaction_costs`, `net_pnl`, `R_multiple`, and `exit_reason`.
- Bar-by-bar Mark-to-Market Equity Curve (`.csv`) with drawdown series.
- Both Dynamic Sizing and Fixed-Lot sensitivity runs to decouple friction from discrete lot-step rounding.

