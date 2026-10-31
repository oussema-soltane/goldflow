# GoldFlow Strategy Configuration Hash Policy

**Policy Version:** 1.0.0 (Phase 6D.1)  
**Effective Date:** 2026-10-29  
**Target Configuration:** `configs/smc_v1_frozen.json`  

---

## 1. Executive Summary

GoldFlow enforces a strict frozen-configuration policy for its primary trading strategy (SMC v1).
To prevent research drift and parameter tuning during out-of-sample or forward evaluation, any
execution attempting to claim canonical SMC v1 status must verify that its configuration matches
the pre-registered baseline.

This document formalizes the two hashing layers used within GoldFlow:
1. **Raw File SHA-256 (`raw_file_sha256`)**: Byte-exact hash of the file as stored on disk.
2. **Canonical Content SHA-256 (`canonical_content_sha256`)**: Platform-independent hash of the parsed JSON AST.

---

## 2. Dual-Hash Specification

### 2.1 Raw File Hash (Baseline Reference)

* **Computation:**
  ```python
  import hashlib
  raw_sha256 = hashlib.sha256(open("configs/smc_v1_frozen.json", "rb").read()).hexdigest()
  ```
* **Canonical Value:**
  ```text
  1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a
  ```
* **Characteristics:**
  - File size: 4,933 bytes
  - Line endings: CRLF (`\r\n`) as committed in repository baseline
  - Environment sensitivity: Susceptible to Git `core.autocrlf` transformations across platforms
  - Role: Enforced by all existing release gates (`EXPECTED_FROZEN_SMC_HASH`)

### 2.2 Canonical Content Hash (Platform-Independent AST)

* **Computation:**
  ```python
  import hashlib, json
  data = json.loads(open("configs/smc_v1_frozen.json", "r", encoding="utf-8").read())
  canonical_json = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
  canonical_sha256 = hashlib.sha256(canonical_json).hexdigest()
  ```
* **Canonical Value:**
  ```text
  2696d34331cd0fa134edea55f7559dda55637bebe27766033155a12997d8a295
  ```
* **Characteristics:**
  - Normalized: Keys sorted alphabetically, whitespace/separators stripped (`','`, `':'`)
  - Line-ending agnostic: Identical output regardless of whether disk uses CRLF or LF
  - Schema-preserving: Reflects exact semantic strategy parameters

---

## 3. Migration and Enforcement Policy

1. **Zero Weakening Invariant:** The existing raw file hash (`1091fb06...`) remains the active gate check in all production code paths (`verify_frozen_config`).
2. **Dual Verification:** Where cross-platform checkout variations may occur, tools may report `canonical_content_sha256` alongside `raw_file_sha256`, but the raw hash must match `1091fb06...` on the official Windows testbed.
3. **Immutability of SMC v1 Strategy Rules:** Under no circumstance may any strategy rule (entry threshold, swing window, risk fraction, stop loss buffer, TP multiple) be modified.

