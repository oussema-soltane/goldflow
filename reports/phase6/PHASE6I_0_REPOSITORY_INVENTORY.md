# GOLDFLOW — PHASE 6I.0
## Repository Inventory and Classification Audit

**Date:** 2026-10-30  
**Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Object Format:** `sha1`  
**Working Directory:** `GoldFlow_SMC_Primary_Updated`  
**Author:** Quantitative Architecture & Security Audit Team  
**Scope:** Exhaustive classification, metrics, and structural integrity audit.

---

## 1. Executive Summary & Inventory Baseline

An exhaustive audit of every file in the GoldFlow repository was performed to establish baseline metrics, eliminate confirmed disposable caches, and categorize all assets into functional and governance tiers.

### Quantitative Summary Table

| Metric | Before Cleanup (Phase 6I) | After Level 1 Cleanup (Phase 6I.0) | Net Difference |
|:---|:---:|:---:|:---:|
| **Total Files (Non-Git)** | **755** | **605** | **-150 files** |
| **Total Repository Size** | **242.47 MB** (254,244,737 bytes) | **239.08 MB** (250,692,425 bytes) | **-3.39 MB net** (-3.58 MB freed) |
| **Tracked Files in Git** | **601** | **601** | **0 (Zero tracked files deleted)** |
| **Untracked Cache Files** | **154** | **0** | **-154 cache files eliminated** |
| **Passed Regression Tests** | **634** | **634** | **0 regressions (100% passing)** |

---

## 2. File Classification Matrix (Categories A through D)

### Category A — Essential Active Project Files (132 files, ~1.52 MB)
These files represent the live codebase, user interfaces, testing frameworks, and active runtime dependencies. All are **PRESERVED**:

| Component Area | File Count | Scope / Description | Key Files |
|:---|:---:|:---|:---|
| **App Entry Point** | 1 | Streamlit multi-page container | `app.py` |
| **UI Pages** | 4 | Interactive dashboards & research pages | `pages/1_Market_Analysis.py`, `pages/2_Backtesting.py`, `pages/3_BI_Dashboard.py`, `pages/4_Strategy_Guide.py` |
| **Core Source (`src/`)** | 45 | Strategy, backtesting, SMC, vault, ingestion | `src/smc/engine.py`, `src/strategy/smc_setups.py`, `src/strategy/smc_research_candidates.py`, `src/backtesting/engine.py`, `src/data/ingestion/bi5_decoder.py`, `src/vault/raw_storage.py` |
| **Regression Tests (`tests/`)** | 42 | Test modules spanning 634 passing tests | `tests/test_phase6i_calibration_readiness.py`, `tests/test_phase6h_simulation_integrity.py`, `tests/test_phase6g_validation.py`, `tests/test_frozen_config_enforcement.py` |
| **Scripts (`scripts/`)** | 19 | Operational and evaluation scripts | `scripts/run_candidate_experiments.py`, `scripts/run_phase5_validation.py`, `scripts/reconcile_feeds.py` |
| **Active Configs (`configs/`)** | 2 | Frozen benchmark & experiment configs | `configs/smc_v1_frozen.json`, `configs/smc_phase5_mtf_experiment.json` |
| **Project Docs (`docs/`)** | 16 | System documentation & hash policies | `docs/HASH_POLICY.md`, `docs/POWER_BI_DESKTOP_GUIDE.md` |
| **Governance & Dependencies** | 3 | Requirements, gitignore, readme | `requirements.txt`, `.gitignore`, `README.md` |

---

### Category B — Historical Research & Audit Evidence (468 files, ~237.52 MB)
These files represent the empirical evidence, trade ledgers, evaluation registrations, and audit trails accumulated across Phases 3 through 6. In accordance with GoldFlow research governance, **NONE ARE DELETED**:

| Component Area | File Count | Size (MB) | Preservation Rationale | Status |
|:---|:---:|:---:|:---|:---:|
| **Canonical Processed Data** | 9 | 7.45 MB | Clean reference bars (`XAUUSD_H1_clean.csv`, `XAUUSD_M5_clean.csv`, `XAUUSD_M15_validation_window.csv`) | **PROTECTED / IMMUTABLE** |
| **Canonical Raw Data** | 4 | 9.93 MB | Original MT5 raw exports | **PROTECTED / IMMUTABLE** |
| **Quarantined Data** | 6 | 0.44 MB | Historical legacy data quarantined due to timestamp drift | **PROTECTED / QUARANTINED** |
| **Synthetic Test Data** | 7 | 0.01 MB | Synthetic fixtures used in unit tests | **PROTECTED / FIXTURES** |
| **Pre-Recovery Archives** | 10 | 1.77 MB | Pre-reingestion historical baseline data | **PROTECTED / ARCHIVED** |
| **Reports Root** | 139 | 136.25 MB | Backtest trade ledgers, metrics, data quality reports | **PRESERVED / INDEXED** |
| **Phase 6 Reports (`reports/phase6/`)**| 33 | 0.32 MB | Architectural audits, security models, calibration plans | **AUTHORITATIVE / ACTIVE** |
| **Strategy Reports (`reports/strategy/`)**| 31 | 1.78 MB | Phase 6F–6H candidate specs, trade logs, loss decomposition | **AUTHORITATIVE / ACTIVE** |
| **Phase 5 Reports (`reports/phase5/`)**| 14 | 23.45 MB | Phase 5 MTF validation outputs and equity curves | **HISTORICAL EVIDENCE** |
| **Phase 3E Reports (`reports/phase3e/`)**| 6 | 23.27 MB | Phase 3E MTF experiment equity curves | **HISTORICAL EVIDENCE** |
| **Synthetic Reports (`reports/synthetic/`)**| 86 | 0.08 MB | Data cleaner audit logs from automated tests | **TEST EVIDENCE** |
| **Archived Reports (`reports/archive/`)**| 66 | 32.70 MB | Pre-recovery and pre-regeneration metrics and logs | **HISTORICAL ARCHIVE** |
| **Evaluation Registrations** | 49 | 0.02 MB | Forward temporal evaluation registrations (`configs/registered_evaluations/`) | **VAULT AUDIT TRAIL** |
| **Investigation Scripts (`scratch/`)** | 8 | 0.05 MB | Reproducible forensic analysis scripts (Phase 6G/6H) | **RESEARCH PROVENANCE** |

---

### Category C — Confirmed Disposable Temporary Files (154 files, 3.42 MB)
These files were confirmed to be compiler-generated or test-generated caches, fully reproducible without any loss of source code, data, or configuration:

| File Type / Directory | Count | Reclaimed Size | Removal Action |
|:---|:---:|:---:|:---:|
| `__pycache__/` directories | 15 dirs (149 `.pyc` files) | 3.36 MB | **REMOVED (Level 1 Cleanup)** |
| `.pytest_cache/` directory | 5 files | 0.06 MB | **REMOVED (Level 1 Cleanup)** |
| **Total Reclaimed** | **154 items** | **3.42 MB** (3,585,182 bytes) | **100% Cleaned** |

---

### Category D — Potentially Obsolete / Review Candidate (1 file, 672 bytes)

| Path | Size | Description | Review Outcome |
|:---|:---:|:---|:---|
| `PHASE3D3_2_RELEASE_NOTE.txt` | 672 B | Historical release note from Phase 3D.3.2 (Calculation-Mode Guard) | **PRESERVED IN ROOT** (Tracked in Git; small file with historical provenance value) |

---

## 3. Cryptographic Invariants Verification

All critical configuration and candidate hashes were re-verified from disk after cleanup:

| File Path | Canonical Expected SHA-256 | Observed SHA-256 | Status |
|:---|:---|:---|:---:|
| `configs/smc_v1_frozen.json` | `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` | `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` | **MATCH** |
| `reports/strategy/phase6h_candidate_spec.json` | `d09474e02c3dc45165a667742cec5012662e58b95cea78bfd6e5e8d782849916` | `d09474e02c3dc45165a667742cec5012662e58b95cea78bfd6e5e8d782849916` | **MATCH** |
| `data/processed/XAUUSD_H1_clean.csv` | Reference MT5 Quote Bar (`2026-10-15 10:00 UTC`: $4,156.94) | Verified on disk | **MATCH** |

---

## 4. Conclusion

The repository is now fully inventoried, documented, and cleansed of disposable compiler/test caches, while 100% of historical research, test evidence, data vaults, and configurations remain pristine and protected.

