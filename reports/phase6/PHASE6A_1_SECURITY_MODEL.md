# GoldFlow Phase 6A.1 Security Model: Holdout Protection, Threat Modeling & Evaluation Integrity

**Author:** Senior Quantitative Research Engineer & Financial Data Architect  
**Date:** 2026-10-28  
**Status:** Hardened, Tested & Verified  
**Canonical Git Revision:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Frozen SMC v1 Configuration SHA-256:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`  

---

## 1. Threat Model & Institutional Scope

GoldFlow is a quantitative research platform for gold (`XAUUSD`) trading designed to maintain rigorous scientific integrity across historical backtesting and forward holdout evaluation.

The goal of this security model is to prevent:
1. **Look-Ahead Bias:** Accidental or intentional leakage of future market observations into strategy decisions.
2. **Multiple Testing & Data Snooping (p-Hacking):** Repeatedly evaluating candidate parameterizations or strategy variants against the same holdout dataset until an overfitted winning result is discovered.
3. **Audit Log Tampering:** Modifying, deleting, or reordering historical access logs or evaluation receipts.
4. **Historical Backfill Spoofing:** Downloading historical data after an evaluation registration timestamp and misclassifying it as untouched forward observations.
5. **Concurrent Evaluation Races:** Running simultaneous evaluation processes against the same holdout vault or dataset before state transitions can be committed.

---

## 2. Windows Access Control & Environment Realities

### 2.1 Advisory Locks vs. OS Security Boundaries
In the legacy implementation, files were marked read-only using `os.chmod(p, stat.S_IREAD)` and Windows `attrib +r`. 

**Critical Security Disclosure:**
- An advisory read-only attribute (`attrib +r`) is **NOT an OS security boundary**.
- In a single-user workstation environment where the researcher operates as a standard user or local administrator, any script or process running under that account can trivially invoke `attrib -r` or `os.chmod(p, stat.S_IWRITE)` and alter or delete files.
- GoldFlow does **not** claim hardware-enforced immutability on a local commodity Windows drive. True protection against tampering in a single-user environment is achieved through **cryptographic evidence** (SHA-256 manifests, hash-chained ledgers, and immutable git commitments) rather than OS-level file locking.

### 2.2 Verified NTFS ACL Architecture
For institutional multi-user deployments (e.g., CI/CD runners, research servers), access control must be enforced at the filesystem level using Windows NTFS Access Control Lists (ACLs).

GoldFlow defines explicit permission policies separating development processes from holdout data:

| Directory | Development Process | Evaluation Service Account (`GoldFlow_Evaluator`) | SYSTEM / Admin |
| :--- | :--- | :--- | :--- |
| `development/` | Full Control `(OI)(CI)(F)` | Read/Write | Full Control |
| `raw_vault/` | Read-Only `(OI)(CI)(R)` | Read/Write (Ingestion only) | Full Control |
| `holdout_vault/` | **NO ACCESS (Denied)** | **Read-Only `(OI)(CI)(R)`** | Full Control |
| `manifests/` | Read-Only `(OI)(CI)(R)` | Append-Only `(OI)(CI)(R,W)` | Full Control |
| `evaluations/` | Read-Only `(OI)(CI)(R)` | Read/Write | Full Control |

The institutional hardening script is generated programmatically via `generate_ntfs_hardening_script(vault_root)`:
```powershell
# Disable inheritance and restrict holdout_vault to evaluation service account
icacls $HoldoutDir /inheritance:d
icacls $HoldoutDir /remove:g "Users" "Authenticated Users"
icacls $HoldoutDir /grant:r "SYSTEM:(OI)(CI)F"
icacls $HoldoutDir /grant:r "Administrators:(OI)(CI)F"
icacls $HoldoutDir /grant:r "GoldFlow_Evaluator:(OI)(CI)R"

# Restrict audit manifests to append-only
icacls $ManifestsDir /inheritance:d
icacls $ManifestsDir /grant:r "SYSTEM:(OI)(CI)F"
icacls $ManifestsDir /grant:r "GoldFlow_Evaluator:(OI)(CI)(R,W)"
```

### 2.3 Programmatic NTFS Inspection
The function `check_ntfs_acl_protection(path)` programmatically runs `icacls`, parses the active security descriptors, checks whether the process is running as administrator or has full control, and emits an objective disclosure of residual administrative risk.

---

## 3. Cryptographic Audit Trail & Hash-Chained Ledgers

Implemented in `src/vault/audit_ledger.py`, `src/vault/holdout.py`, and `src/vault/raw_storage.py`.

### 3.1 Hash-Chained Audit Ledger Architecture
Both `ingestion_history.jsonl` and `holdout_access_audit.log` are managed by `TamperEvidentAuditLedger`. Every record is cryptographically linked to its predecessor via SHA-256:

$$\text{Entry Hash}_i = \text{SHA-256}\Big(\text{Entry Hash}_{i-1} \,\|\, \text{Canonical JSON Payload}_i\Big)$$

For the genesis record ($i = 0$), $\text{Entry Hash}_{-1} = 0^{64}$.

```
+--------------------------+       +--------------------------+       +--------------------------+
| Entry 0 (Genesis)        |       | Entry 1                  |       | Entry 2                  |
| index: 0                 | ----> | index: 1                 | ----> | index: 2                 |
| prev_hash: 0000...0000   |       | prev_hash: SHA(Entry 0)  |       | prev_hash: SHA(Entry 1)  |
| payload: {event: INIT}   |       | payload: {event: SEAL}   |       | payload: {event: ACCESS} |
| entry_sha256: 4a2f...    |       | entry_sha256: 9b1e...    |       | entry_sha256: c7d3...    |
+--------------------------+       +--------------------------+       +--------------------------+
```

### 3.2 Chain Verification & Tamper Detection
The method `ledger.verify_chain()` scans the entire file sequentially:
1. Verifies that `entry_index` is strictly contiguous ($0, 1, 2, \dots$).
2. Verifies that `prev_entry_sha256` exactly matches the hash of record $i-1$.
3. Recomputes `entry_sha256` and verifies it matches the recorded digest.

If any line is modified, deleted, inserted, or reordered, `verify_chain()` immediately fails with the exact index and diagnostic description.

### 3.3 Integrity Checking vs. Source Authentication
**Crucial Distinction:**
- A valid SHA-256 hash proves **data integrity** (the file has not been altered since the hash was calculated).
- A valid SHA-256 hash does **NOT prove source authentication** (it does not prove that LMAX, Dukascopy, or an ECN generated the data).
- True source authentication requires cryptographic digital signatures (e.g. Ed25519) signed by the data provider's private key, or TLS certificate chain verification during direct live streaming. Because historical broker CSVs lack provider signatures, GoldFlow transparently labels them as `declared_not_independently_verified`.

---

## 4. Evaluation Lifecycle & Concurrency Protection

Implemented in `src/vault/evaluation_gate.py`.

### 4.1 Inter-Process Mutual Exclusion (`GateProcessLock`)
To prevent concurrent race conditions where two processes attempt to evaluate the same vault simultaneously, `EvaluationGate` acquires `evaluations/gate.lock` via atomic file creation (`os.O_CREAT | os.O_EXCL | os.O_RDWR`).
- If another process holds the lock and its PID is alive, execution raises `ConcurrentEvaluationError`.
- If the lock exists but the recorded PID is dead (e.g., from a crash or killed process), `GateProcessLock` automatically reclaims the stale lock, logs the event to the audit trail, and proceeds safely.

### 4.2 Explicit Lifecycle States
Every evaluation registration transitions through an explicit state machine:

```
[ REGISTERED ] 
       │
       ▼ (Acquire Lock & Start)
  [ RUNNING ] ───────────► (Exception / Crash) ──────────► [ FAILED ]
       │                                                         │
       ▼ (Execution Success)                                     ▼
[ EVALUATED_CONSUMED ]                              (Preserved in Audit Log;
(Receipt Emitted; Holdout Locked)                    Cannot Silently Succeed)
```

1. `REGISTERED`: Pre-registration committed; strategy git hash, frozen config SHA-256, and boundary $T_{\text{reg}}$ sealed.
2. `RUNNING`: Inter-process lock acquired; PID, caller, and start timestamp recorded.
3. `FAILED`: If an exception occurs or the process crashes, the registration is transitioned to `FAILED` with error type, message, and traceback. It is **never** silently marked as successful.
4. `EVALUATED_CONSUMED`: Execution succeeded; cryptographic receipt emitted; holdout datasets permanently locked.

### 4.3 Dataset-Level Consumption Lock
To prevent a researcher from evaluating Dataset A under Registration 1, and then evaluating the same Dataset A under Registration 2 (data snooping / parameter tuning), `EvaluationGate` maintains `{vault_root}/evaluations/consumed_datasets.json`.
- Records `dataset_sha256`, `dataset_name`, `registration_id`, and `consumed_at_utc`.
- If ANY evaluation request targets a dataset hash already recorded in the registry, execution aborts with `DatasetAlreadyConsumedError`.

### 4.4 Crash Recovery (`recover_interrupted_evaluations`)
If an evaluation process crashes or is killed while in `RUNNING`:
- `recover_interrupted_evaluations()` scans all registrations.
- Checks if the recorded PID is alive.
- If the PID is dead, transitions status to `FAILED` with failure reason `"PROCESS_TERMINATED_ABNORMALLY"`.
- Recovery preserves the full audit trail and prevents silent reruns.

---

## 5. Forward-Data Eligibility & Dual-Timestamp Standard

Implemented in `src/data/ingestion/models.py` and `src/vault/evaluation_gate.py`.

### 5.1 Dual-Timestamp Formulation
To prevent historical backfill from being passed off as forward out-of-sample data, GoldFlow enforces a dual-timestamp model:
1. **Market Observation Time ($T_{\text{obs}}$):** The physical timestamp of the quote/trade in the financial market.
2. **Ingestion Receipt Time ($T_{\text{ingest}}$):** The trusted timestamp when GoldFlow received and recorded the data.

### 5.2 Mathematical Forward Eligibility Rule
An observation $\text{obs}$ is forward-eligible for evaluation registration $R$ with boundary $T_{\text{reg}}$ if and only if:

$$\forall \text{obs} \in \text{Dataset}, \quad T_{\text{obs}}(\text{obs}) \ge T_{\text{reg}} \quad \land \quad T_{\text{ingest}}(\text{obs}) \ge T_{\text{reg}}$$

### 5.3 Threat Scenarios Addressed
1. **Pre-Registration Data:** A dataset downloaded before registration has $T_{\text{ingest}} < T_{\text{reg}}$ and is rejected with `PRE-REGISTRATION INGESTION REJECTED`.
2. **Historical Backfill:** A researcher registers on November 1 ($T_{\text{reg}} = \text{2026-11-01}$), but downloads historical data from October ($T_{\text{obs}} = \text{2026-10-15}$). Even though $T_{\text{ingest}} \ge T_{\text{reg}}$, $T_{\text{obs}} < T_{\text{reg}}$. The gate immediately rejects it with `HISTORICAL BACKFILL REJECTED`.
3. **Boundary Observations:** Observations where $T_{\text{obs}} = T_{\text{reg}}$ and $T_{\text{ingest}} \ge T_{\text{reg}}$ are legitimately accepted.

### 5.4 Clock Synchronization Assumptions
- System clock assumes synchronization via Network Time Protocol (NTP / Windows Time Service) with maximum expected clock skew $\le 500\text{ms}$.
- Timestamps are strictly parsed as UTC using ISO 8601 representation.

---

## 6. Raw Data Preservation & Instrument Limits

Implemented in `src/data/ingestion/validator.py`.

### 6.1 Configurable Instrument Limits
Price bounds are decoupled from hardcoded logic via `InstrumentPriceLimits`:
- `DEFAULT_GOLD_LIMITS`: `XAUUSD`, min \$500.0, max \$10,000.0, max spread \$50.0.
- `DEFAULT_FX_LIMITS`: `EURUSD`, min 0.50, max 3.00, max spread 0.0100.
Custom profiles can be passed per instrument.

### 6.2 Sequence-Aware Deduplication
In high-frequency ECN market feeds, multiple transactions legitimately execute within the same millisecond. 
- The validator inspects `(timestamp_utc, bid, ask, volume, sequence_id)`.
- If sequence IDs differ, observations are treated as **distinct market events** and are never dropped.
- Ticks are dropped as duplicates only when sequence IDs match or when unsequenced ticks have identical timestamps, prices, and volumes.

### 6.3 Raw Ingestion Capture
If `raw_archive_dir` is configured, incoming raw observations are written to disk **prior** to validation or filtering, and the raw file's SHA-256 hash is recorded in `ValidationAuditReport`.

---

## 7. M1 Bar Synthesis & Traceability

Implemented in `src/data/ingestion/bar_builder.py`.

- **Interval Semantics:** Left-closed, right-open $[T, T+60\text{s})$.
  - Tick at `10:00:00.000` $\to$ bar `10:00:00`.
  - Tick at `10:00:59.999` $\to$ bar `10:00:00`.
  - Tick at `10:01:00.000` $\to$ bar `10:01:00`.
- **Price Source Transparency:** Synthesizer explicitly records whether bars represent `bid`, `ask`, or `mid` prices.
- **Empty Intervals:** **Zero synthetic candles are manufactured during market closures or weekend gaps.** Only intervals containing actual ticks produce bars.
- **Source Traceability:** `AggregatedBar` preserves `first_sequence_id` and `last_sequence_id`, mapping every synthesized candle directly back to its underlying raw tick sequence bounds.

