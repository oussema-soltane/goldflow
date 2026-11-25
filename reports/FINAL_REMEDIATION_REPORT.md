# GOLDFLOW — FINAL ENGINEERING REMEDIATION REPORT

**Date:** 2026-11-11  
**Project:** GoldFlow — ICT Market Structure & Trading Analytics Platform  
**Target:** Engineering Audit, Remediation, and Backlog Resolution  

---

## 1. Prioritized Remediation Summary

Following Section 19 of the Master Forensic Engineering Directive, issues were resolved in strict priority order (P0 -> P1 -> P2 -> P3).

---

## 2. Priority 0 — Research & Data Integrity

### 2.1 Overwrite Guard Hardened to Fail-Closed (`pages/1_Market_Analysis.py`)
- **Defect:** An exception in the row-count inspection of an existing raw file was caught with `except Exception: pass`, leaving `_allow_save = True`. Additionally, when the new live fetch returned an equal number of rows (5,000 bars), it replaced canonical historical files with date-shifted live data.
- **Remediation:** 
  * Replaced with a fail-closed architecture. Any file inspection error explicitly sets `_allow_save = False` and displays a critical error banner.
  * Overwriting existing canonical datasets in `data/raw/` from the interactive Streamlit UI is strictly prohibited. Live data is loaded into session memory for exploratory inspection without mutating on-disk canonical files.
  * Audited updates must be executed via `scripts/download_data.py` with explicit promotion controls.

### 2.2 Restoration of Quarantined Datasets
- **Action:** Datasets `data/raw/XAUUSD_H4_raw.csv` and `data/raw/XAUUSD_M15_raw.csv` (and their processed counterparts) were restored from git commit `d75ca98`.
- **Integrity Verified:**
  * H4 raw SHA-256: `9bf68ed4b607aa91ededf95df03f42e552a1f52b0b0238373730756a579bb149` (5,000 rows)
  * M15 raw SHA-256: `b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075` (5,000 rows)
  * The overwritten files were preserved in `data/quarantine/20261111_overwrite_event/` for forensic traceability.

### 2.3 Expanded Data Readiness Scanner (`src/research/data_readiness.py`)
- **Defect:** `audit_all_datasets` scanned only `*_clean.csv`, completely ignoring validation window files.
- **Remediation:**
  * Scanner now discovers all `*_validation_window.csv` files.
  * Implemented an automated cross-check that intersects timestamps of the validation window against the clean dataset of the same timeframe.
  * Any detected overlap triggers a `CRITICAL CONTAMINATION` warning in both datasets' audit reports.

---

## 3. Priority 1 — Core Strategy & Backtesting Engine

### 3.1 Partial-Profit & Fixed R:R Execution Engine (`src/backtesting/engine.py`)
- **Specification:** Implemented support for ADR-006 candidate strategy `SMC_CANDIDATE_FIXED_RR_v1`.
- **Parameters Added:** `partial_exit_at_r: float = 0.0`, `remaining_exit_at_r: float = 0.0`.
- **Execution Logic:**
  * When configured (`partial_exit_at_r > 0` and `remaining_exit_at_r > partial_exit_at_r`), eligible orders are split into two sub-positions at entry:
    - Leg A (50% lots): target price = `entry ± partial_exit_at_r * stop_distance`.
    - Leg B (50% lots): target price = `entry ± remaining_exit_at_r * stop_distance`.
  * **Lot Conservation:** Lots are allocated from the rounded total position (`leg_a_lots = floor(lots/2)`, `leg_b_lots = lots - leg_a_lots`), guaranteeing exact lot conservation without odd micro-lot leakage.
  * Both legs share the origin stop-loss.
  * When left at `0.0` (default), the engine runs the exact baseline single-position strategy with opposing liquidity targets.

### 3.2 Candidate Specification Formally Sealed
- Candidate specification files `configs/candidate_specs/SMC_CANDIDATE_FIXED_RR_v1.json` and `.py` committed.
- Includes locked validation period protocol and non-anticipative promotion criteria (PF >= 1.10, Max DD <= 20% on development data).

---

## 4. Priority 2 — Visualization & Interactive UI

### 4.1 Four Presets & Sub-Second Rendering (`src/visualization/charts.py`)
- **Clean Price Action:** Candlesticks, volume, and structure breaks only (<0.07s).
- **SMC Analysis (Institutional Default):** Focuses on actionable nearby structure with proximity filtering (`vis_span * 0.35`) and `max_zones_per_type = 8` (<0.15s).
- **Full SMC Research:** Displays all historical zones, open/mitigated/invalidated, with toggleable Y-axis expansion (<0.35s).
- **Custom:** User-configurable overlays.
- Dynamic Y-axis framing locks price axis to visible OHLC (+8% padding), preventing candle flattening.
- Weekend gap suppression via Plotly rangebreaks eliminates market closure visual voids.

---

## 5. Priority 3 — Testing & Verification

- Added regression tests in `tests/test_download_safety.py` (fail-closed guard).
- Added unit tests in `tests/test_candidate_fixed_rr.py` (split order execution & lot conservation).
- Full suite executed: **664 passed in 31.21s** (0 failures).
- Re-generated comprehensive inventory in `reports/FORENSIC_FILE_REVIEW_LEDGER.csv` (905 files).

