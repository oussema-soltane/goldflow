# GOLD FLOW — Phase 6D.1 Comprehensive Data Integrity Audit

**Document Class:** System Integrity Audit & Vulnerability Assessment  
**Phase:** 6D.1 — Comprehensive Data Integrity, Vault Security, Evaluation Gate and Research Reconciliation  
**Date:** 2026-10-29  
**Auditor:** Senior Quantitative Research Engineer, Python Architect & Testing Specialist  
**Repository Identity:** `ad9807f8405811d65148d73d72139243f3d6a77f` (object format: sha1)  
**Strategy Config Baseline Hash:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`  

---

## 1. Executive Summary

This audit establishes the actual physical repository state and documents critical defects identified across the GoldFlow research pipeline. Prior documentation contained erroneous Git identifiers and non-hexadecimal strings resulting from character encoding issues (UTF-8 em-dash decoded as `?"` or corrupted base64 suffixes). The actual Git revision is verified as clean SHA-1 `ad9807f8405811d65148d73d72139243f3d6a77f`.

The audit identified twelve (12) high-severity architectural, data-integrity, and security vulnerabilities that threatened research reproducibility, forward-evaluation independence, and execution safety.

---

## 2. Baseline Verification & Source-Control Analysis

### 2.1 Git Repository Identity

Direct interrogation of the underlying Git database confirms:
- **`git rev-parse --verify HEAD`**: `ad9807f8405811d65148d73d72139243f3d6a77f`
- **`git rev-parse --show-object-format`**: `sha1`
- **`git log -1 --format="%H%n%h%n%s"`**:
  ```text
  ad9807f8405811d65148d73d72139243f3d6a77f
  ad9807f
  first commit
  ```
- **Disproven Claim:** Earlier reports cited `ad9807f8405819eWJh8J6Mx9DrGXKEv3ojKmqw8Cv9pscK`. This string contained invalid non-hexadecimal characters (`W`, `J`, `h`, `M`, `x`, `D`, `r`, `G`, `X`, `K`, `E`, `v`, `o`, `j`, `m`, `q`, `w`, `C`, `v`, `p`, `s`, `c`, `K`) arising from an upstream buffer concatenation/encoding error. The true commit hash is valid 40-character hexadecimal.

### 2.2 Working-Tree Categorization

* **Committed Baseline:** Revision `ad9807f` contains the initial project scaffolding.
* **Tracked Modified Files (17):** Core engine, loader, cleaner, backtesting engine, dashboards, and safety tests modified in-tree during Phases 1–6D.
* **Cumulative Phase Modules:**
  - `src/data/ingestion/`: Provider-neutral interfaces, BI5 decoder, instrument specifications.
  - `src/vault/`: Holdout manager, evaluation gate, registration manager, audit ledger.
  - `reports/phase5/`, `reports/phase6/`: Verified research artifacts and audit receipts.
  - `data/synthetic/`: Deterministic test fixtures.

### 2.3 Frozen Configuration Hashing Analysis

* **Exact File Bytes:** 4,933 bytes with CRLF (`\r\n`) line terminators.
* **Raw File SHA-256:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a` (Unchanged, byte-exact match).
* **Canonical JSON Content SHA-256:** `2696d34331cd0fa134edea55f7559dda55637bebe27766033155a12997d8a295`.
  - Canonical normalization strips platform line endings, sorts dictionary keys, and standardizes separators (`','`, `':'`).
  - Documented in `docs/HASH_POLICY.md`.

---

## 3. Vulnerability & Defect Register

### Defect 1: Raw-Data Storage Overwrite & Monthly Partitioning Bug
* **Vulnerability:** `PartitionStorageManager.get_partition_path()` mapped hourly data into a monthly filename (`{SYMBOL}_{PROVIDER}_{YYYYMM}.parquet`). `os.replace()` then silently overwrote the monthly partition whenever a new hour was ingested.
* **Impact:** Loss of historical raw data; inability to store multiple hours; violation of append-only architecture.
* **Manifest Key Bug:** `dukascopy_provider.py` queried `manifest_dict.get("sha256")`, but the manifest key was `"file_sha256"`, causing `partition_sha256` to record as `None`.

### Defect 2: Ingestion Timestamp Fabrication (Backdating)
* **Vulnerability:** `RawTickObservation.__post_init__` defaulted `ingestion_time_utc` to `observation_time_utc` when `None`.
* **Impact:** Historical data downloaded years after the event appeared to have been ingested contemporaneously with the market quotes, completely subverting forward-evaluation temporal gating.

### Defect 3: Unverified XAUUSD Price Scale Bypass
* **Vulnerability:** `execute_bounded_retrieval_pilot()` called `spec.validate_for_decoding(allow_unverified=self.allow_unverified_scale)`. Setting `allow_unverified_scale=True` (intended only for synthetic test fixtures) bypassed the gate for real network retrieval.
* **Impact:** Potential ingestion of real market data with an unverified scaling factor ($100 vs $1000).

### Defect 4: HTTP 404 Silent Success & Unbounded Network Pilot
* **Vulnerability:** In `dukascopy_provider.py`, HTTP 404 set `raw_bytes = b""` and proceeded as an empty batch. No response size limits or redirect domain validations existed.
* **Impact:** Non-existent data treated as valid empty data; potential denial of service via oversized payload; open redirects.

### Defect 5: Evaluation Gate Fail-Open on Registry Corruption
* **Vulnerability:** `EvaluationGate.get_consumed_datasets()` returned `{}` upon encountering any exception during file reading or JSON parsing.
* **Impact:** A corrupted, truncated, or tampered `consumed_datasets.json` registry converted consumption protection into an open gate, permitting re-evaluation of consumed holdout data.

### Defect 6: Evaluation Gate Loose Dataset Matching
* **Vulnerability:** `verify_pre_evaluation()` only checked that supplied datasets in the list existed in registration, but did not reject unexpected additional datasets or detect missing registered datasets.
* **Impact:** Unregistered files could be smuggled into an evaluation pass.

### Defect 7: Incomplete First-Row Forward Eligibility Check
* **Vulnerability:** `_verify_forward_eligibility()` inspected only row 0 of the Parquet table.
* **Impact:** Subsequent rows containing historical backfill or out-of-order leakage were ignored.

### Defect 8: Hash-Chain Ledger Blind Append
* **Vulnerability:** `TamperEvidentAuditLedger.append_entry()` only read the last line's hash to compute the next hash, without verifying preceding links.
* **Impact:** An attacker could modify historical audit entries and append new ones without detection.

### Defect 9: Incomplete MT5 Transactional Rollback
* **Vulnerability:** `transactionally_stage_and_promote()` backed up existing files, but if target files did not exist prior to promotion and promotion failed partway, the newly created targets were left behind.
* **Impact:** Incomplete or corrupted datasets left in production directories after failed acquisitions.

### Defect 10: Phase 5 Regression Test Timeframe Filter Bug
* **Vulnerability:** `test_cost_replay_exact_reconciliation_zero_cent_difference` looped over `("M15", "M5")`, but filtered `df[df["timeframe"] == "M15"]` in both iterations.
* **Impact:** M5 was never tested, giving a false sense of test coverage.

### Defect 11: Bid-Side Volume Truncation
* **Vulnerability:** Dukascopy `.bi5` records include both `ask_volume` and `bid_volume`, but `RawTickObservation` discarded `bid_volume`.
* **Impact:** Loss of provider quote granularity.

### Defect 12: Missing Production Dependencies
* **Vulnerability:** `pyarrow` and `scipy` were utilized by vault storage and analysis modules but omitted from `requirements.txt`.
* **Impact:** Clean-room deployment failure.

---

## 4. Remediation Mandate

All twelve defects require systematic remediation accompanied by strict regression tests exercising the actual public API workflows. The frozen SMC v1 configuration rules and ICT engine isolation must remain strictly inviolate.

