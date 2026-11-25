# GOLDFLOW — PHASE 6I: STAGE D
## 12–24 Month Historical XAUUSD Data Acquisition Plan

**Date:** 2026-10-30  
**Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Object Format:** `sha1`  
**Target Symbol:** `XAUUSD`  
**Author:** Quantitative Architecture & Data Engineering Team  
**Prerequisite:** Stage B/C Price-Scale Calibration Execution & Formal Promotion to `VERIFIED`

---

## 1. Overview and Objectives

Phase 6H demonstrated that all currently existing M15 bar observations in the GoldFlow repository have been examined, leaving zero eligible untouched data for independent statistical evaluation of candidate **C2 (Target Rationalized 2.0R)**.

To conduct a statistically sound evaluation with high statistical power ($N \ge 400\text{–}900$ interim trades; $N \approx 3,300$ asymptotic trades), GoldFlow must acquire **12 to 24 contiguous months** of high-resolution XAUUSD historical data.

This document establishes the end-to-end engineering, crawling, storage, resampling, and holdout segregation architecture for that historical ingestion campaign.

---

## 2. Source Ingestion Architecture

### 2.1 Provider and Transport
- **Provider:** Dukascopy Bank SA (SWFX Marketplace public historical archive)
- **Transport:** HTTPS GET over TLS from verified zero-cost public CDN endpoint (`datafeed.dukascopy.com`)
- **Format:** LZMA-compressed big-endian binary archives (`.bi5`) containing 20-byte tick records (`>3I2f`)
- **Estimated Data Volume (24 Months):**
  - Trading hours: $\approx 12,500$ hourly partitions (accounting for weekend closures)
  - Raw compressed `.bi5` volume: $\approx 2.5\text{ GB} - 4.5\text{ GB}$
  - Decoded tick records: $\approx 150\text{M} - 250\text{M}$ ticks
  - Resampled M15 OHLCV bars: $\approx 50,000$ bars

### 2.2 Directory Layout & Storage Hierarchy
The ingestion pipeline writes into an immutable, hierarchical vault structure managed by `PartitionStorageManager`:

```text
data/vault/dukascopy/
├── raw/                                  <-- Immutable compressed .bi5 sources
│   └── XAUUSD/
│       └── YYYY/
│           └── MM/
│               └── DD/
│                   └── {HH}h_ticks.bi5
├── partitions/                           <-- Decoded, validated Parquet partitions
│   └── XAUUSD/
│       └── hourly/
│           └── YYYY/
│               └── MM/
│                   └── DD/
│                       ├── XAUUSD_YYYYMMDD_HH.parquet
│                       └── XAUUSD_YYYYMMDD_HH.meta.json  <-- SHA-256 & provenance
├── resampled/                            <-- Aggregated OHLCV bars
│   ├── XAUUSD_M1.parquet
│   └── XAUUSD_M15.parquet
└── manifests/                            <-- Ingestion batch ledgers & logs
    └── acquisition_ledger_24m.jsonl
```

---

## 3. Crawler Governance & Rate-Limiting Policy

To guarantee responsible consumption of the public CDN and eliminate risk of IP throttling (HTTP 429), the ingestion crawler will adhere to strict polite crawling parameters:

| Parameter | Specification | Purpose |
|:---|:---:|:---|
| **Max Concurrent Workers** | `2` parallel threads | Avoid connection saturation |
| **Inter-Request Delay** | `250 ms` to `500 ms` (jittered) | Emulate polite automated retrieval |
| **User-Agent String** | `GoldFlow-Quant-Research/2.0 (Non-Commercial Academic Pilot)` | Clear audit identification |
| **HTTP 429 Backoff** | Exponential backoff ($2^n \times 1.0\text{s}$) up to 60s | Immediate compliance with rate limits |
| **HTTP 5xx Retries** | Max 3 retries with jitter | Resilient against transient CDN glitch |
| **Batch Checkpointing** | Persisted after every 24 hourly partitions | Resumable without duplicate requests |

---

## 4. Handling Missing Hours & Market Closures

Dukascopy returns HTTP 404 or 0-byte responses for hours when no trading occurred. The ingestion worker will classify non-200 responses deterministically:

1. **Weekend Closures:**
   - From Friday 21:00 UTC through Sunday 21:00 UTC.
   - HTTP 404 / empty payload is expected and classified as `SCHEDULED_WEEKEND_CLOSURE`.
   - Recorded in manifest with zero tick count; no retry.
2. **Scheduled Holidays:**
   - New Year's Day, Christmas Day, Easter market closures.
   - Classified as `SCHEDULED_HOLIDAY_CLOSURE`.
3. **Mid-Week Missing Hours:**
   - Any HTTP 404 occurring during active trading sessions (e.g. Tuesday 14:00 UTC).
   - Classified as `ANOMALY_MISSING_FEED`.
   - Logged to `acquisition_exceptions.jsonl` and queued for verification against secondary calendar.

---

## 5. Resampling Pipeline (Ticks $\to$ M1 $\to$ M15)

High-fidelity SMC backtesting requires bar timestamps to be mathematically unambiguous.

### 5.1 Bar Boundary & Timestamp Invariant
- **Interval Convention:** Left-closed, right-open $[t, t + \Delta t)$.
- **Timestamp Label:** `time` column represents the start of the interval in strict UTC (e.g., `10:00:00+00:00` represents ticks from `10:00:00.000` to `10:14:59.999`).
- **OHLC Derivation:**
  - `open`: First valid tick Bid price in interval.
  - `high`: Maximum valid tick Bid price in interval.
  - `low`: Minimum valid tick Bid price in interval.
  - `close`: Last valid tick Bid price in interval.
- **Volume & Spread Derivation:**
  - `tick_volume`: Count of decoded tick observations in interval.
  - `spread`: Time-weighted median bid-ask spread across all ticks in the interval.
  - `real_volume`: Sum of tick ask/bid volume amounts.

### 5.2 Empty Bar Imputation
If a 15-minute interval during active market hours contains zero ticks:
- Impute with flat bar: `open = high = low = close = previous_close`.
- `tick_volume = 0`, `real_volume = 0.0`.
- Flagged with boolean column `imputed = True`.

---

## 6. Three-Tier Chronological Holdout Partitioning

To maintain absolute scientific validity and prevent any form of look-ahead or selection bias, the acquired 24-month dataset will be partitioned into three strict chronological segments:

```
Month 1                               Month 12  Month 13            Month 18  Month 19              Month 24
[─────────────────── 12 Months ──────────────────][───── 6 Months ─────][───── 6 Months ─────]
          TRAINING & EXPLORATION                    VALIDATION HOLDOUT       TEST / OUT-OF-SAMPLE
         (Model & Parameter Tuning)                (C2 Single-Pass Gate)     (Cryptographically Sealed)
```

### 6.1 Segment A: Exploration & Training Window (Months 1–12)
- **Role:** Available for open exploratory analysis, feature extraction, market structure calibration, and parameter bounds check.
- **Access Level:** Open research access.

### 6.2 Segment B: Validation Holdout (Months 13–18)
- **Role:** Independent validation gate for frozen candidate strategies (specifically **C2 Target Rationalized 2.0R**).
- **Access Level:** Single-pass evaluation only. No post-hoc parameter adjustments permitted based on validation performance.

### 6.3 Segment C: Final Test Holdout (Months 19–24)
- **Role:** Final out-of-sample evaluation gate.
- **Access Level:** **Cryptographically Sealed**. Partition directory is checksummed and write-locked. Only accessed once a strategy candidate has passed all Segment B criteria and received formal research committee sign-off.

---

## 7. Execution Timeline and Milestones

1. **Milestone 1:** Stage B/C Price-Scale Calibration Execution on 2026-10-15 10:00 UTC (1 single hour).
2. **Milestone 2:** Promotion of `DUKASCOPY_XAUUSD_SPEC` to `VERIFIED`.
3. **Milestone 3:** Ingestion pilot of 1 full week (5 trading days, ~120 hours).
4. **Milestone 4:** Full 24-month ingestion execution with polite crawler (~24-48 hours elapsed time).
5. **Milestone 5:** Resampling to M1 and M15 OHLCV Parquet files with integrity audit.
6. **Milestone 6:** Sealing of Segment C holdout and delivery of Segment B to Phase 6J C2 evaluation.

