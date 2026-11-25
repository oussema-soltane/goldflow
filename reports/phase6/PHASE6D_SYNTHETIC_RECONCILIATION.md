# GoldFlow Historical Cross-Provider Feed Reconciliation Report

**Author:** Senior Quantitative Research Engineer
**Date:** 2026-10-28 23:04:41 UTC
**Audit Status:** RECONCILIATION_COMPLETED

---

## 1. Input Datasets & Manifest Hashes

| Attribute | Primary Dataset (MT5 / Reference) | Comparison Dataset (Dukascopy / Feed) |
| :--- | :--- | :--- |
| **File Name** | `provider_a_xauusd.csv` | `provider_b_xauusd.csv` |
| **SHA-256 Digest** | `0af910df7d5a4401461926302b9400e06c299a1bf1196a26c772b3824f76d169` | `ad72c8569bc746736fdda65a810708a5d7a7e331ef33b2b83e0c723524a6af05` |
| **Total Rows** | 6 | 5 |
| **Time Range** | 2024-10-01T08:00:00+00:00 $\to$ 2024-10-01T08:04:30+00:00 | 2024-10-01T08:00:00+00:00 $\to$ 2024-10-01T08:04:30+00:00 |

---

## 2. Temporal Overlap & Alignment Summary

- **Overlapping UTC Window:** `2024-10-01T08:00:00+00:00` $\to$ `2024-10-01T08:04:30+00:00` (0.07 hours)
- **Aligned Common Bars:** 5
- **Primary Exclusive Bars (Missing in Comparison):** 1
- **Comparison Exclusive Bars (Missing in Primary):** 0
- **Duplicate Timestamps:** Primary: 0, Comparison: 0

---

## 3. Price Deviation & OHLC Variance

| Field | Mean Diff | MAE | RMSE | Max Diff | P50 (Median) | P95 Diff | Exceeding Tol. (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |

---

## 4. Spread Distribution Comparison

| Feed | Field | Mean Spread | Median Spread | Min Spread | Max Spread | P95 Spread |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |

---

## 5. Architectural Reconciliation & Disclaimers

HISTORICAL CROSS-PROVIDER FEED RECONCILIATION: This audit compares historical pricing structures across two feeds to evaluate broker markup, spread widening, and liquidity differences. It does NOT constitute forward temporal validation and must not be used as evidence of strategy profitability.

- **Pricing Mechanism Variance:** Retail MT5 broker feeds incorporate proprietary broker spread markups (typically 15–30¢ on XAUUSD) and synthetic filtering. Institutional ECN feeds (such as Dukascopy SWFX) reflect raw matching-engine top-of-book quotes with tighter baseline spreads but microsecond volatility.
- **Session Rollover Differences:** Gaps during daily bank maintenance (21:00–22:00 UTC) frequently exhibit different tick frequencies across venues.