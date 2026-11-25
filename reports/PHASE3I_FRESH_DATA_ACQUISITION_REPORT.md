# PHASE 3I: FRESH HISTORICAL DATA ACQUISITION & INTEGRITY AUDIT
**Subsystem:** Financial Data Engineering, Market Feed Ingestion & Holdout Preservation  
**Auditor:** Lead Financial Data Engineer & Independent Research Auditor  
**Acquisition Architecture:** `data/research/phase3i/`  
**Manifest File:** `data/research/phase3i/manifests/PHASE3I_DATA_INTEGRITY_MANIFEST.json`  
**Audit Status:** **INFRASTRUCTURE ESTABLISHED (AWAITING UNCONSUMED DATA INGESTION)**  
**Audit Date:** 2026-11-17  

---

## 1. Executive Summary

To satisfy Non-Negotiable Rules 9 and 10, candidate `SMC_CONFLUENCE_V2` cannot be evaluated against previously consumed historical data. The primary historical research dataset (`data/research/phase3/processed/XAUUSD_M15_extended.csv`) terminates on **October 20, 2026 at 15:45:00 UTC**.

This audit investigated four potential avenues for acquiring unconsumed XAU/USD market data:
1. **Live MetaTrader 5 Terminal IPC Connection:** Tested directly via Python. The terminal is not running on the host system (`IPC initialize failed, MetaTrader 5 x64 not found`).
2. **Local Repository Data Assets:** An exhaustive recursive scan confirmed that all existing clean, raw, and validation files in `data/` terminate on or before October 20, 2026. Zero unconsumed post-October 2026 or pre-October 2024 data exists locally.
3. **Dedicated Ingestion Architecture:** A physically isolated directory hierarchy was created at `data/research/phase3i/` with subdirectories `raw/`, `processed/`, `manifests/`, and `quarantine/`.
4. **Prospective Evaluation Guard:** A fail-closed evaluation runner (`scripts/run_prospective_evaluation.py`) was deployed. It automatically hashes target datasets and blocks execution if a candidate is tested against any known consumed dataset.

---

## 2. Forensic Investigation of Data Sources

### 2.1 MetaTrader 5 IPC Terminal Test
The Python script `scratch/check_mt5_live.py` was executed to determine whether historical rates could be pulled from a live local MT5 terminal:

```
[Execution Output]
MetaTrader 5 Python package: INSTALLED (version 5.0.45)
mt5.initialize() Call:       FAILED
Error Code:                  -10003
Error Description:           'IPC initialize failed, MetaTrader 5 x64 not found'
```
**Conclusion:** No local MetaTrader 5 terminal process is currently active or listening on IPC sockets on this Windows host. Automated broker data export via MT5 IPC is currently offline.

### 2.2 Local Repository Scan
All CSV data files across the workspace were audited for time coverage:
- `data/raw/XAUUSD_M5_raw.csv`: Terminated October 20, 2026 (99,999 bars) — **CONSUMED**.
- `data/research/phase3/processed/XAUUSD_M15_extended.csv`: Terminated October 20, 2026 (33,388 bars) — **CONSUMED**.
- `data/processed/XAUUSD_M15_clean.csv`: Terminated 2025 (24,960 bars) — **CONSUMED**.
- `data/processed/XAUUSD_M15_validation_window.csv`: Terminated 2025 (5,760 bars) — **QUARANTINED**.
- `data/_archive_pre_reingest_20261014/`: Truncated legacy raw files — **QUARANTINED**.

**Finding:** Zero unconsumed historical market data currently exists within the repository.

---

## 3. Phase 3I Isolated Data Architecture

To ensure that future ingested data remains completely sequestered from historical research artifacts, the following dedicated directory hierarchy has been established:

```
data/
└── research/
    ├── phase3/
    │   ├── consumed/       <-- Existing Phase 3 datasets permanently marked consumed
    │   ├── processed/      <-- XAUUSD_M15_extended.csv (LOCKED)
    │   └── raw/            <-- XAUUSD_M5_raw.csv (LOCKED)
    └── phase3i/
        ├── raw/            <-- Destination for fresh raw tick/M5 broker exports
        ├── processed/      <-- Destination for resampled, completeness-tagged M15 bars
        ├── manifests/      <-- Cryptographic manifests and broker provenance metadata
        └── quarantine/     <-- Defective or corrupted candidate feeds
```

---

## 4. Ingestion Specification for Unconsumed Data

To qualify as a valid prospective evaluation dataset for `SMC_CONFLUENCE_V2`, newly ingested data must fulfill the following formal technical criteria:

1. **Eligible Time Horizons:**
   - **Option A (Forward Prospective Window):** Continuous M5/M15 bars covering October 21, 2026 through the latest calendar date.
   - **Option B (Pre-October 2024 Historical Window):** Continuous M5/M15 bars covering January 1, 2023 through September 30, 2024 that have never been backtested in GoldFlow.
2. **Contract Specifications (Institutional Standard):**
   - Symbol: `XAUUSD`
   - Contract Size: 100 troy ounces.
   - Tick Size: \$0.01 USD.
   - Tick Value: \$1.00 USD.
   - Timezone: UTC strictly enforced (`tz_convert('UTC')`).
   - Timestamp Convention: Interval start timestamp (left-labeled, left-closed `[t, t+15m)`).
3. **Data Quality Protocols:**
   - Zero synthetic candles or zero-volume flatline interpolation.
   - Mandatory completeness metadata tagging (`is_complete`, `observed_m5_count`, `session_boundary_reason`).
   - Sourced from a certified institutional liquidity provider (e.g. Dukascopy, LMAX, Darwinex, or MetaQuotes-Demo broker export).

---

## 5. Current Research Governance Status

In accordance with strict quantitative research governance:
- `SMC_CONFLUENCE_V2` evaluation is **SUSPENDED** pending acquisition of unconsumed data.
- The evaluation runner `scripts/run_prospective_evaluation.py` will automatically reject execution on any consumed dataset.
- Research integrity is certified intact.

