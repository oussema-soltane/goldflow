# GOLDFLOW — RESEARCH CONTAMINATION & HOLDOUT AUDIT

**Date:** 2026-11-11  
**Scope:** Investigation of `data/processed/XAUUSD_M15_validation_window.csv` (509 rows), Overlap Detection, Phase 6 Consumption Records, and Independent Holdout Policy  
**Auditor:** Quantitative Research & Research Integrity Auditor

---

## 1. Validation Window Investigation & Overlap Analysis

The project contains a designated validation dataset:
`data/processed/XAUUSD_M15_validation_window.csv` (509 rows, SHA-256: `794f095a82a582200e4260b572aa68f08875ce321d902eb2610c16694657ced3`).

A forensic record-by-record comparison was executed across the datasets:

### Comparison 1: Canonical Baseline vs. Validation Window
- **Canonical `XAUUSD_M15_clean.csv`:** 5,000 rows | `2026-08-04 12:00:00+00:00` to `2026-10-22 09:15:00+00:00`
- **Validation Window:** 509 rows | `2026-10-22 09:30:00+00:00` to `2026-10-29 22:30:00+00:00`
- **Result:** **0 overlapping rows** (0 matching timestamps).
- The validation window strictly starts 15 minutes after the canonical clean dataset ends. In the canonical git baseline, physical data contamination between the files does not exist.

### Comparison 2: Quarantined 2026-11-04 Overwrite vs. Validation Window
- **Quarantined `XAUUSD_M15_clean.csv`:** 5,000 rows | `2026-08-17 21:15:00+00:00` to `2026-11-04 13:30:00+00:00`
- **Validation Window:** 509 rows | `2026-10-22 09:30:00+00:00` to `2026-10-29 22:30:00+00:00`
- **Result:** **509 overlapping rows (100% overlap)**!
- **Critical Finding:** When the 2026-11-04 live fetch overwrote `XAUUSD_M15_clean.csv`, the entire 509-bar validation window was ingested into the primary training dataset. In that state, any backtest or strategy calculation on `data/processed/XAUUSD_M15_clean.csv` suffered from direct data leakage and holdout contamination.

---

## 2. Research History & "Consumed" Holdout Status

A review of `configs/registered_evaluations/` (over 70 registered JSON records) and `reports/phase6/` documentation reveals that the period `2026-10-22` to `2026-10-29` was already evaluated repeatedly during Phase 6 forward temporal testing.

### Academic Research Rule
Once a holdout dataset has been evaluated to assess strategy performance, its hypothesis-testing independence is destroyed. It cannot be recycled as an "untouched validation window" for subsequent candidate strategy tuning. Doing so constitutes p-hacking and look-ahead bias.

### Verdict on Current Validation Window
- Status: **CONSUMED / EXAMINED**.
- It is retained in `data/processed/` for historical reproduction of Phase 6 reports only.
- It is **strictly prohibited** from serving as the independent out-of-sample holdout for any new SMC strategy candidate.

---

## 3. Independent Holdout Protocol for Future Research

For the newly defined candidate strategy experiment `SMC_CANDIDATE_FIXED_RR_v1`:

1. **Development Period (60% split):**
   - H4: `2023-07-27` to `2025-06-30`
   - H1: `2025-01-31` to `2025-11-30`
   - M15: `2026-08-04` to `2026-09-15`
   - M5: `2025-05-13` to `2025-11-30`

2. **Validation Period (40% split - LOCKED):**
   - H4: `2025-07-01` to `2026-10-20`
   - H1: `2025-12-01` to `2026-10-20`
   - M15: `2026-09-16` to `2026-10-22`
   - M5: `2025-12-01` to `2026-10-20`
   - **Protocol:** Evaluated strictly once. No parameter tuning, threshold modification, or rule adjustments are permitted after evaluating the validation split.

3. **True Out-of-Sample Final Gate:**
   - Any live deployment or forward claim requires fresh broker data post-dating `2026-11-04`, ingested through the audited downloader and cryptographically sealed before execution.
