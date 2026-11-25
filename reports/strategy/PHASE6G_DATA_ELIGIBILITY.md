# PHASE 6G — Data Eligibility Report

**GoldFlow XAUUSD Research Platform**
**Phase 6G — Dataset Provenance, Classification, and Evaluation Plan**
**Date:** 2026-10-30 | **Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`

---

## 1. Complete Dataset Inventory

| File | Rows | First UTC | Last UTC | Interval | SHA-256 (first 16 chars) |
|------|------|-----------|---------|----------|--------------------------|
| `data/processed/XAUUSD_M5_clean.csv` | 99,999 | 2025-05-13 22:15 | 2026-10-20 15:50 | 5 min | `76d3d4fc95069694…` |
| `data/processed/XAUUSD_M15_clean.csv` | 5,000 | 2026-08-04 12:00 | 2026-10-22 09:15 | 15 min | `2f6bded7fc58752a…` |
| `data/processed/XAUUSD_H1_clean.csv` | 10,000 | 2025-01-31 14:00 | 2026-10-20 14:00 | 1 hr | `2192f4c1f22010a7…` |
| `data/processed/XAUUSD_H4_clean.csv` | 5,000 | 2023-07-27 17:00 | 2026-10-20 09:00 | 4 hr | `3a5f3342899e7539…` |
| `data/raw/XAUUSD_M15_raw.csv` | 1,500 | 2026-10-07 03:45 | 2026-10-29 22:30 | 15 min | `bd347dc95f84a786…` |
| `data/raw/XAUUSD_M5_raw.csv` | 99,999 | 2025-05-13 22:15 | 2026-10-20 15:50 | 5 min | `7c5c5187bbb65933…` |
| `data/raw/XAUUSD_H1_raw.csv` | 10,000 | 2025-01-31 14:00 | 2026-10-20 14:00 | 1 hr | `ed050b1b273d0801…` |
| `data/raw/XAUUSD_H4_raw.csv` | 5,000 | 2023-07-27 17:00 | 2026-10-20 09:00 | 4 hr | `9bf68ed4b607aa91…` |

---

## 2. Research History Classification

### XAUUSD_M15_clean.csv (5,000 bars, 2026-08-04 → 2026-10-22)

**Classification: EXAMINED DEVELOPMENT DATA — DO NOT REUSE AS HOLDOUT**

Used in:
- Phase 3E: MTF structure experiment (initial SMC M15 analysis)
- Phase 5: Phase 5 validation pipeline
- Phase 6F: All six candidate simulations (C0–C5) run on the full 5,000 bars

The candidate selection decision (preferring C1 and C2) was made after observing results on this dataset. These 5,000 bars are contaminated by selection bias — any positive result from re-running on them cannot constitute independent evidence.

### XAUUSD_M5_clean.csv (99,999 bars, 2025-05-13 → 2026-10-20)

**Classification: EXAMINED DEVELOPMENT DATA**

Used in Phase 6F M5 simulations. All six candidates were run. Loss decomposition was performed. Session analysis (discovering NY Afternoon edge) was performed on this dataset. Any session filter derived from it is data-mined, not independently verified.

### XAUUSD_H1_clean.csv / XAUUSD_H4_clean.csv

**Classification: EXAMINED DEVELOPMENT DATA**

Used as HTF context for C5 (MTF Aligned) candidate.

### XAUUSD_M15_raw.csv — bars beyond 2026-10-22 09:15 UTC

**Classification: CANDIDATE EVALUATION DATA (Untouched)**

The `data/raw/XAUUSD_M15_raw.csv` file (modified after initial commit, shown as `M` in `git status`) contains 1,500 bars. The processed M15 dataset ends at 2026-10-22 09:15 UTC. The raw file contains **509 bars** (2026-10-22 09:30 → 2026-10-29 22:30 UTC) that are strictly beyond the processed dataset's boundary.

These 509 bars were never used in any Phase 6F or earlier analysis. They were not available to the candidate development process. They constitute the only genuinely untouched M15 data available.

**Provenance note:** This raw file is marked as modified in `git status`, indicating it was appended to at some point after the initial commit (2026-10-23). This is consistent with it having been downloaded as a data collection activity during Phases 6D–6E. No analysis was performed on the post-2026-10-22 portion in any documented phase.

---

## 3. Chronological Data Map

```
2023-07  ────────────────────────────────  H4 data starts
2025-01  ──────────────────────────────── H1 data starts
2025-05  ──────────────────────────────── M5 data starts
2026-08-04  M15 development data starts
               │
               │  ◄── All Phase 6F analysis performed here
               │
2026-10-22 09:15  ◄── BOUNDARY: Last processed M15 bar
2026-10-22 09:30  ◄── Validation window starts (509 bars)
               │
               │  ◄── UNTOUCHED data begins here
               │
2026-10-29 22:30  ◄── Validation window ends (all available M15 data)
```

---

## 4. Price Scale Verification

> [!IMPORTANT]
> The fail-closed XAUUSD price scale gate (range $2,500–$3,200) is implemented in `src/data/ingestion/dukascopy/decoder.py` and applies to the Dukascopy BI5 ingestion pathway only. It does NOT apply to the local CSV loader (`load_local_data`).

The processed M15 dataset shows prices $4,062–$4,693. The validation window shows prices $3,977–$4,098. The M5 dataset spans $3,125–$5,589. All datasets use the same price scale (current spot gold in USD, no cent scaling).

The original fail-closed gate threshold of $2,500–$3,200 appears to reflect an outdated XAUUSD range that was correct when the ingestion module was first written (Phases 6C–6D). The gate does not block the local CSV validation path.

**No synthetic or fabricated data was used. The 509-bar window is genuine market data from the raw file.**

---

## 5. Evaluation Plan (Pre-committed Before Inspecting Results)

The following was determined before running any validation simulations:

1. **Eligible evaluation data:** 509 M15 bars (2026-10-22 09:30 → 2026-10-29 22:30 UTC)
2. **Candidates to evaluate:** C0, C1, C2 — specifications frozen before any validation run
3. **Same BacktestConfig** as Phase 6F: $10,000 capital, 1% risk, $0.20 spread/side, $0.05 slippage/side
4. **All three candidates on the same window** — no cherry-picking of date ranges per candidate
5. **No parameter changes** after seeing validation results
6. **No additional candidates** developed against the validation window

---

## 6. Limitations

1. **509 bars = 7 calendar days** (2026-10-22 to 2026-10-29): This is an extremely short window. SMC setups occur roughly once per 100–200 M15 bars in development data. Expectation: 2–8 trades per candidate, far below any statistically meaningful threshold.

2. **Single contiguous week:** Market behavior during one specific week cannot represent the full range of volatility regimes, trend conditions, and liquidity events that a strategy would face over its operational lifetime.

3. **Selection bias not resolved:** The session filter (07:00–21:00 UTC) was discovered by examining M15 development data. Any validation on the 509-bar window addresses "does it work in the next 7 days" not "does it work in general."

4. **Cannot acquire more data:** The fail-closed ingestion gate requires explicit operator authorization before any external data download. That authorization has not been granted. No additional data can be ingested.

**Conclusion: The validation window exists but is insufficient for a meaningful evaluation. Results must be reported honestly as directional observations, not statistical conclusions.**

