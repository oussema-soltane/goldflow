# GOLDFLOW — DATA INTEGRITY & PROVENANCE AUDIT

**Date:** 2026-11-11  
**Scope:** Canonical Raw and Processed Datasets (XAUUSD H4, H1, M15, M5), Overwrite Incidents, Timestamp Modes, and Future-Candle Anomalies  
**Auditor:** Quantitative Data & Research Integrity Engineering Team

---

## 1. Canonical Dataset Provenance & Baseline Verification

All active raw and clean datasets on disk were inspected record-by-record and their cryptographic hashes compared against the canonical baseline:

| Timeframe | Dataset Path | Row Count | Date Range (UTC) | SHA-256 Hash | Integrity Status |
|---|---|---|---|---|---|
| **H1 (Raw)** | `data/raw/XAUUSD_H1_raw.csv` | 10,000 | 2025-01-31 14:00 to 2026-10-20 14:00 | `ed050b1b273d08014f007c7fe98eb1d81a321c8a3c2d5e9c22a0df7ea9574dbb` | **CANONICAL_MATCH** |
| **H1 (Clean)** | `data/processed/XAUUSD_H1_clean.csv` | 10,000 | 2025-01-31 14:00 to 2026-10-20 14:00 | `2192f4c1f22010a78c2fc17f37a1826254f8ee4060df1dc813814ea559321db9` | **CANONICAL_MATCH** |
| **H4 (Raw)** | `data/raw/XAUUSD_H4_raw.csv` | 5,000 | 2023-07-27 17:00 to 2026-10-20 09:00 | `9bf68ed4b607aa91ededf95df03f42e552a1f52b0b0238373730756a579bb149` | **CANONICAL_MATCH** |
| **H4 (Clean)** | `data/processed/XAUUSD_H4_clean.csv` | 5,000 | 2023-07-27 17:00 to 2026-10-20 09:00 | `3a5f3342899e7539ddf6b40f098091dfb6c5ea3ae3219da64016d92789b670fc` | **CANONICAL_MATCH** |
| **M15 (Raw)** | `data/raw/XAUUSD_M15_raw.csv` | 5,000 | 2026-08-04 12:00 to 2026-10-22 09:15 | `b893bc507daec515d36ff51cb988e4f6e33df23f3ccddd6924794b64fbe7b075` | **CANONICAL_MATCH** |
| **M15 (Clean)** | `data/processed/XAUUSD_M15_clean.csv` | 5,000 | 2026-08-04 12:00 to 2026-10-22 09:15 | `2f6bded7fc58752a7de9097c9258bb24840be79fbaad55d82ebf4835dfad2def` | **CANONICAL_MATCH** |
| **M5 (Raw)** | `data/raw/XAUUSD_M5_raw.csv` | 99,999 | 2025-05-13 22:15 to 2026-10-20 15:50 | `7c5c5187bbb6593391708a5842e06b72ca7c1474ea86d91c2aac0e7e8a051257` | **CANONICAL_MATCH** |
| **M5 (Clean)** | `data/processed/XAUUSD_M5_clean.csv` | 99,999 | 2025-05-13 22:15 to 2026-10-20 15:50 | `76d3d4fc95069694b46a1492e4755017cb0e7571ab78570493ec3de1a4a8fa8c` | **CANONICAL_MATCH** |
| **M15 (Val)** | `data/processed/XAUUSD_M15_validation_window.csv` | 509 | 2026-10-22 09:30 to 2026-10-29 22:30 | `794f095a82a582200e4260b572aa68f08875ce321d902eb2610c16694657ced3` | **CANONICAL_MATCH** |

---

## 2. Forensic Investigation of the 2026-11-04 Overwrite Event

### Incident Reproduction & Root Cause
At the start of the audit, on-disk H4 and M15 datasets were found to be modified relative to git HEAD:
- On-disk M15 had hash `f9f5f42d107a0d462839d745fe928005d8589d9ea110b13c5091e99465bce603`
- On-disk H4 had hash `baa18758c6864ec415ede8042f40c030e05301328b19f1d6ed6d069c208939ab`
- Both files were quarantined immediately to `data/quarantine/20261111_overwrite_event/`.

Inspection of the quarantined metadata (`XAUUSD_M15_clean_ondisk_20261111.meta.json`) revealed:
1. `retrieval_date_utc`: `2026-11-04T11:47:55.656265+00:00`
2. `end_time`: `2026-11-04T13:30:00+00:00`
3. `timestamp_mode`: `posix_utc`

### The 7 Future-Candle Anomaly Explained
- In November, standard time in Europe/Athens is EET (UTC+2 / offset +7200s), following the Daylight Saving Time transition on the last Sunday of October (2026-10-25).
- The MT5 server time at retrieval was **13:47:55 EET** (which equals **11:47:55 UTC**).
- The latest completed 15-minute bar on the server was 13:30 EET.
- Because `posix_utc` was selected during retrieval, the MT5 server epoch was not adjusted by -7200 seconds.
- The candle was erroneously labeled as `13:30:00 UTC`, which was 1 hour 42 minutes **into the future** relative to `retrieval_date_utc` (11:47:55 UTC).
- This generated exactly 7 apparent future candles:
  `11:45, 12:00, 12:15, 12:30, 12:45, 13:00, 13:15, 13:30`.
- **Conclusion:** The future candles were a direct symptom of uncorrected timezone offsets (`posix_utc` instead of `server_wall_clock` with `Europe/Athens`).

### Fail-Open Guard Vulnerability
The overwrite guard in `pages/1_Market_Analysis.py` originally checked:
`if len(df_raw) < _existing_rows: disallow_save`
Because the new live fetch returned exactly 5,000 bars (matching the existing 5,000 rows), `len(df_raw) < _existing_rows` evaluated to `False`. The guard silently allowed the overwrite to proceed, replacing canonical historical data with date-shifted live data.

### Remediation Applied
1. Canonical datasets were restored from git commit `d75ca98`.
2. `pages/1_Market_Analysis.py` was hardened with a **fail-closed** safeguard:
   - Any inspection error strictly sets `_allow_save = False`.
   - Silent overwriting of existing canonical files from the UI is unconditionally blocked.
   - Live data is loaded into session memory for interactive analysis without mutating canonical on-disk files.
   - Regression tests `test_canonical_overwrite_guard_fails_closed_on_unreadable_file` and `test_canonical_overwrite_guard_blocks_shrinkage` were implemented in `tests/test_download_safety.py`.

---

## 3. Timestamp Semantics & Offset Verification

All canonical datasets preserve original MT5 raw epoch timestamps in column `time_raw_epoch` and explicit offsets in `timestamp_correction_applied_seconds`:
- **Winter bars (EET, UTC+2):** offset = `-7200` seconds. Example: H1 row 0 `time_raw_epoch = 1738339200` (2025-01-31 16:00 local) -> normalized `2025-01-31 14:00:00+00:00`.
- **Summer bars (EEST, UTC+3):** offset = `-10800` seconds. Example: H4 row 0 `time_raw_epoch = 1690488000` (2023-07-27 20:00 local) -> normalized `2023-07-27 17:00:00+00:00`.
- Historical transition dates between EEST and EET are handled deterministically without fixed single-offset assumptions.
