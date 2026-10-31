# GOLD FLOW — Phase 6D.1 Test Evidence & Verification Receipt

**Document Class:** Cryptographic & Execution Test Evidence  
**Phase:** 6D.1 — Comprehensive Data Integrity, Vault Security, Evaluation Gate and Research Reconciliation  
**Date:** 2026-10-29  
**Execution Environment:** Windows (x86_64), Python 3.14.7, pytest 9.1.1  
**Git Baseline Commit:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Test Suite Result:** ✅ **544 PASSED / 0 FAILED / 0 SKIPPED** (Duration: 23.48s)  
**External Network Calls:** ZERO (0)  

---

## 1. Full Test Suite Verification

### 1.1 Test Execution Command & Terminal Output

```powershell
$ cd "c:\Users\ousse\Downloads\GoldFlow_Ultimate_Updated\GoldFlow_SMC_Primary_Updated"
$ python -m pytest tests/ -q --tb=short
........................................................................ [ 13%]
........................................................................ [ 26%]
........................................................................ [ 39%]
........................................................................ [ 52%]
........................................................................ [ 66%]
........................................................................ [ 79%]
........................................................................ [ 92%]
........................................                                 [100%]
544 passed in 23.48s
```

* **Total Test Cases:** 544
* **Passed:** 544
* **Failed:** 0
* **Errors:** 0
* **Exit Code:** 0

---

## 2. Phase 6D.1 Focused Remediation Test Suite

Command: `python -m pytest tests/test_phase6d1_remediation.py -v`

| Test Name | Module / Class | Result |
| :--- | :--- | :--- |
| `test_two_distinct_hours_produce_separate_shard_files` | `TestImmutableStorageAndPartitioning` | ✅ PASSED |
| `test_repeated_ingestion_of_identical_hour_is_idempotent` | `TestImmutableStorageAndPartitioning` | ✅ PASSED |
| `test_conflicting_content_same_partition_name_is_rejected` | `TestImmutableStorageAndPartitioning` | ✅ PASSED |
| `test_original_compressed_bytes_persisted_separately` | `TestImmutableStorageAndPartitioning` | ✅ PASSED |
| `test_manifest_contains_both_sha256_keys` | `TestImmutableStorageAndPartitioning` | ✅ PASSED |
| `test_historical_observation_ingestion_time_is_none_by_default` | `TestIngestionTimestampProvenance` | ✅ PASSED |
| `test_explicit_ingestion_time_is_preserved_when_supplied` | `TestIngestionTimestampProvenance` | ✅ PASSED |
| `test_bid_volume_is_preserved` | `TestIngestionTimestampProvenance` | ✅ PASSED |
| `test_real_network_ingestion_unconditionally_rejects_unverified_xauusd` | `TestRealXAUUSDIngestionGate` | ✅ PASSED |
| `test_synthetic_fixture_spec_cannot_authorize_real_network_ingestion` | `TestRealXAUUSDIngestionGate` | ✅ PASSED |
| `test_provider_real_network_pilot_refuses_xauusd_even_with_allow_unverified_flag` | `TestRealXAUUSDIngestionGate` | ✅ PASSED |
| `test_http_404_raises_data_unavailable` | `TestHttpSafetyGates` | ✅ PASSED |
| `test_http_403_raises_authentication_error` | `TestHttpSafetyGates` | ✅ PASSED |
| `test_http_429_raises_rate_limit_error` | `TestHttpSafetyGates` | ✅ PASSED |
| `test_oversized_response_is_rejected` | `TestHttpSafetyGates` | ✅ PASSED |
| `test_attempt_to_write_into_holdout_vault_is_blocked` | `TestHttpSafetyGates` | ✅ PASSED |
| `test_corrupted_consumed_registry_fails_closed` | `TestEvaluationGateHardening` | ✅ PASSED |
| `test_extra_unregistered_dataset_rejected` | `TestEvaluationGateHardening` | ✅ PASSED |
| `test_missing_registered_dataset_rejected` | `TestEvaluationGateHardening` | ✅ PASSED |
| `test_per_row_temporal_leakage_detected` | `TestEvaluationGateHardening` | ✅ PASSED |
| `test_corrupted_chain_blocks_append` | `TestAuditLedgerTamperEvidentChain` | ✅ PASSED |
| `test_rollback_removes_newly_created_files_when_later_step_fails` | `TestMT5TransactionalRollback` | ✅ PASSED |
| `test_raw_file_sha256_matches_baseline` | `TestFrozenConfigHashPolicy` | ✅ PASSED |
| `test_canonical_json_content_hash_stability` | `TestFrozenConfigHashPolicy` | ✅ PASSED |

---

## 3. Core Engine Isolation & Frozen Configuration Gates

Command: `python -m pytest tests/test_canonical_isolation.py tests/test_frozen_config_enforcement.py -v`

| Test Suite | Tests | Result |
| :--- | :--- | :--- |
| `tests/test_canonical_isolation.py` (Canonical & synthetic isolation guards) | 6 | ✅ 6 PASSED |
| `tests/test_frozen_config_enforcement.py` (Frozen schema & hash gates) | 9 | ✅ 9 PASSED |

---

## 4. Operational Scripts & Environmental Verification

1. **Python Bytecode Compilation:**
   ```powershell
   $ python -m compileall -q src scripts tests pages
   # Exit code: 0 (No syntax errors detected)
   ```
2. **Research Readiness Audit:**
   ```powershell
   $ python scripts/research_readiness.py
   # Status: READY_WITH_WARNINGS (Expected: MT5 offline mode active)
   ```
3. **Execution Specification Audit:**
   ```powershell
   $ python scripts/audit_execution_specs.py
   # Status: MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE
   ```
4. **Git Diff Hygiene Check:**
   ```powershell
   $ git diff --check
   # Exit code: 0 (Zero merge conflict markers, zero trailing whitespace errors)
   ```
5. **Frozen SMC v1 Configuration Cryptographic Seal:**
   ```powershell
   $ python -c "import hashlib; print(hashlib.sha256(open('configs/smc_v1_frozen.json','rb').read()).hexdigest())"
   1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a
   ```

---

## 5. Security & Isolation Invariants

- **No live trading credentials or connections:** VERIFIED.
- **No external provider downloads performed:** VERIFIED (All tests mock HTTP or run on deterministic synthetic fixtures).
- **Holdout isolation:** VERIFIED (Holdout vault remains unconsumed).
- **SMC v1 trading rules:** BYTE-EXACT UNCHANGED.
- **ICT engine independence:** VERIFIED.

