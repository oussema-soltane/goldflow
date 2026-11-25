# GOLD FLOW — Phase 6D.1 Remediation & Architectural Hardening Report

**Document Class:** System Remediation Report  
**Phase:** 6D.1 — Comprehensive Data Integrity, Vault Security, Evaluation Gate and Research Reconciliation  
**Date:** 2026-10-29  
**Author:** Senior Quantitative Research Engineer, Python Architect & Testing Specialist  
**Repository Identity:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Configuration SHA-256 (Raw):** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`  
**Configuration SHA-256 (Canonical):** `2696d34331cd0fa134edea55f7559dda55637bebe27766033155a12997d8a295`  

---

## 1. Executive Summary

This report documents the architectural and security remediations implemented during Phase 6D.1. Every defect identified in `PHASE6D_1_INTEGRITY_AUDIT.md` has been corrected through surgical modifications to existing production components without rebuilding the application, altering frozen SMC v1 trading rules, or performing external network requests.

---

## 2. Detailed Technical Remediations

### 2.1 Fix 1: Raw-Data Storage Overwrite & Hourly Partitioning
* **Files Modified:** `src/vault/raw_storage.py`, `src/data/ingestion/dukascopy_provider.py`
* **Root Cause:** `get_partition_path()` defaulted any granularity other than `"daily"` to monthly (`%Y%m`), causing multiple hourly batches to target the exact same file. `os.replace()` then silently overwrote previous hours.
* **Remediation:**
  1. Updated `get_partition_path()` to explicitly support `granularity="hourly"`, generating deterministic timestamps formatted as `YYYYMMDD_HH`.
  2. Implemented strict immutability checks in `write_partition()`:
     - If the target file already exists and matches the candidate SHA-256, the operation is treated as idempotent, logged as `PARTITION_IDEMPOTENT_SKIPPED`, and returns the existing partition without rewriting.
     - If the target file already exists and possesses a conflicting SHA-256, the operation is rejected, logged as `PARTITION_CONFLICT_REJECTED`, and raises `PartitionConflictError`.
  3. Added `write_source_object()` to persist original compressed source bytes (e.g. `.bi5`) separately in `source_objects/` alongside their cryptographic manifests.
  4. Fixed manifest key lookup in `dukascopy_provider.py` (`manifest_dict.get("file_sha256") or manifest_dict.get("sha256")`) and added dual-key entries in manifests.

### 2.2 Fix 2: Ingestion Timestamp Provenance
* **Files Modified:** `src/data/ingestion/models.py`, `src/data/ingestion/bi5_decoder.py`
* **Root Cause:** `RawTickObservation.__post_init__` defaulted `ingestion_time_utc` to `observation_time_utc` when `None`.
* **Remediation:**
  1. Removed automatic defaulting: when `ingestion_time_utc` is `None`, it remains `None`.
  2. Added `has_known_ingestion_time` boolean property.
  3. Added `DatasetClassification` enum (`HISTORICAL_ARCHIVE`, `FORWARD_REAL_TIME`, `UNKNOWN`).
  4. Updated `bi5_decoder.py` to classify decoded ticks as `DatasetClassification.HISTORICAL_ARCHIVE` with `ingestion_time_utc=None`.
  5. Preserved `bid_volume` alongside `volume` (ask-side) in `RawTickObservation` and `to_dict()`.

### 2.3 Fix 3: Real XAUUSD Network Ingestion Gate Hardening
* **Files Modified:** `src/data/ingestion/instrument_spec.py`, `src/data/ingestion/dukascopy_provider.py`
* **Root Cause:** Ingestion pilot called `validate_for_decoding(allow_unverified=self.allow_unverified_scale)`, allowing synthetic testing flags to bypass real data gates.
* **Remediation:**
  1. Added `validate_for_real_network_ingestion()` to `ProviderInstrumentSpec`. This method accepts NO override flags and fails closed unconditionally unless `verification_status == VerificationStatus.VERIFIED`.
  2. Replaced `validate_for_decoding` in `execute_bounded_retrieval_pilot` with `validate_for_real_network_ingestion()`.
  3. Real XAUUSD ingestion remains strictly blocked until empirical calibration evidence is produced.

### 2.4 Fix 4: HTTP and Retrieval Safety Hardening
* **Files Modified:** `src/data/ingestion/dukascopy_provider.py`
* **Root Cause:** HTTP 404 was treated as empty success; responses were unbounded; no redirect verification existed; holdout vault could be targeted.
* **Remediation:**
  1. HTTP 404 now raises `DataUnavailableError("HTTP_404_NOT_FOUND")`.
  2. HTTP 403 raises `AuthenticationError("HTTP_403_FORBIDDEN")`.
  3. HTTP 429 raises `IngestionError("HTTP_429_RATE_LIMITED")`.
  4. Server errors (5xx) trigger bounded exponential backoff retries.
  5. Enforced maximum response size bound of 50 MB (`MAX_RESPONSE_BYTES`).
  6. Enforced host redirection check: redirected responses not beginning with `https://datafeed.dukascopy.com` raise `IngestionError("UNAUTHORIZED_REDIRECT")`.
  7. Empty (0-byte) responses raise `DataUnavailableError("EMPTY_RESPONSE")`.
  8. Output storage directory cannot target or enter holdout vault paths (`STORAGE VIOLATION`).

### 2.5 Fix 5: Evaluation Gate Fail-Closed Registry & Exact Matching
* **Files Modified:** `src/vault/evaluation_gate.py`
* **Root Cause:** Read/JSON errors in `consumed_datasets.json` returned `{}` (fail-open); only a subset check of registered datasets was conducted.
* **Remediation:**
  1. `get_consumed_datasets()` now raises `EvaluationGateError("REGISTRY INTEGRITY FAILURE")` on any read or parse failure. Only `FileNotFoundError` (clean initial state) returns `{}`.
  2. `verify_pre_evaluation()` now enforces exact bijection: unexpected extra datasets raise `EvaluationGateError("UNREGISTERED DATASETS SUPPLIED")`; missing datasets raise `EvaluationGateError("REGISTERED DATASETS MISSING")`.
  3. Replaced single-row inspection in `_verify_forward_eligibility()` with full-column vector checks over all rows for both `timestamp_utc` and `ingestion_time_utc`. Any row predating the registration boundary triggers `ForwardEligibilityError`.
  4. Added path traversal security checks rejecting directory escapes and symlink tricks.

### 2.6 Fix 6: Audit Ledger Chain Verification Before Append
* **Files Modified:** `src/vault/audit_ledger.py`
* **Root Cause:** `append_entry()` only linked to the last line's hash without validating historical links.
* **Remediation:**
  - `append_entry()` now invokes `self.verify_chain()` prior to appending any entry. If the existing ledger is broken or tampered with at any position, `ValueError` is raised and the append is blocked.

### 2.7 Fix 7: MT5 Transactional Promotion Rollback
* **Files Modified:** `scripts/download_data.py`
* **Root Cause:** Promotion rollback only tracked files that existed before the transaction; newly created files from partially successful promotions were orphaned.
* **Remediation:**
  - `transactionally_stage_and_promote()` now tracks `newly_created` targets. Upon any promotion exception, pre-existing files are restored from backups, and any newly created target files are explicitly deleted.

### 2.8 Fix 8: Phase 5 Regression Test Timeframe Filter
* **Files Modified:** `tests/test_phase5_regression.py`
* **Root Cause:** Test loop filtered `df["timeframe"] == "M15"` regardless of loop variable.
* **Remediation:**
  - Corrected filter to `df[(df["timeframe"] == tf) & (df["strategy_variant"] == variant)]`. Both M15 and M5 are now independently tested.

### 2.9 Fix 9: UI Integrity & Holdout Label Corrections
* **Files Modified:** `pages/1_Market_Analysis.py`, `pages/2_Backtesting.py`
* **Root Cause:** Hardcoded `True` in incomplete candle exclusion; misleading "Untouched Holdout" phrasing for previously examined data.
* **Remediation:**
  - Replaced hardcoded status with dynamic/honest indicator (`✅ Verified Excluded` vs `⚠️ Unverified / Declared`).
  - Updated Backtesting UI to clearly label historical test segments as `Historical Exploratory Segment (Previously Examined)`.

### 2.10 Fix 10: Dependency Declarations
* **Files Modified:** `requirements.txt`
* **Remediation:**
  - Declared `pyarrow>=14.0.0` and `scipy>=1.13.0`.

