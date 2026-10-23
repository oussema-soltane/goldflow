# GoldFlow — Data Quality Report

**Audit Status:** 🟡 PASSED WITH WARNINGS
- **Symbol:** `XAUUSD`
- **Timeframe:** `M15`
- **Total Bars Analyzed:** 1,500
- **Date Range:** 2026-09-28 11:30:00 UTC to 2026-10-21 12:15:00 UTC
- **Generated At:** 2026-10-21 09:41:14 UTC

## 1. Summary of Integrity Checks

| Check | Status | Details |
| :--- | :--- | :--- |
| **Chronological Order** | ✅ PASS | Timestamps strictly monotonic |
| **Duplicate Timestamps** | ✅ PASS | 0 duplicate timestamp(s) found |
| **Missing Values (NaN)** | ✅ PASS | 0 total missing cell(s) |
| **OHLC Consistency** | ✅ PASS | 0 invalid OHLC row(s) |
| **Expected Weekend Gaps** | ℹ️ INFO | 3 standard market closure period(s) |
| **Abnormal Market Gaps** | ⚠️ WARNING | 14 unexpected trading gap(s) |
| **Incomplete Active Bar** | ✅ PASS | Active candle excluded |

## 3. Data Quality Warnings

- ⚠️ Detected 14 abnormal intraday/weekday gap(s) exceeding normal M15 interval.

## 4. Abnormal Time Gaps (Intraday/Weekday)

| Gap Start | Gap End | Duration (min) | Notes |
| :--- | :--- | :--- | :--- |
| 2026-09-28 22:45:00+00:00 | 2026-09-29 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-09-29 22:45:00+00:00 | 2026-09-30 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-09-30 22:45:00+00:00 | 2026-10-01 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-10-01 22:45:00+00:00 | 2026-10-02 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-10-05 22:45:00+00:00 | 2026-10-06 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-10-06 22:45:00+00:00 | 2026-10-07 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-10-07 22:45:00+00:00 | 2026-10-08 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-10-08 22:45:00+00:00 | 2026-10-09 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-10-12 22:45:00+00:00 | 2026-10-13 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| 2026-10-13 22:45:00+00:00 | 2026-10-14 01:00:00+00:00 | 135.0 | Missing ~9 bars during active market hours |
| ... | ... | ... | *(4 more gaps omitted)* |

---
*Report generated automatically by GoldFlow Data Pipeline. Zero price interpolation applied.*
