# GoldFlow Phase 6A Architecture: Forward Data Infrastructure & Independent Holdout Vault

**Author:** Senior Quantitative Research Engineer & Financial Data Architect  
**Date:** 2026-10-28  
**Status:** Implemented & Verified  
**Scope:** Provider-Neutral Ingestion, Parquet Vault Storage, Holdout Isolation, Pre-Registration Gate & Deterministic Bar Synthesis  

---

## 1. System Overview & Architectural Motivation

GoldFlow is an institutional-grade quantitative research platform for gold (`XAUUSD`) trading, centered on Smart Money Concepts (SMC) as the primary strategy and a canonically isolated Inner Circle Trader (ICT) engine.

Following the Phase 5 backtest reconciliation and Phase 5.1 release gate (which resolved higher-timeframe data leakage and unified baseline cost replays to \$0.00 difference), Phase 6A introduces the **forward data infrastructure** and **independent holdout vault**. 

The fundamental problem Phase 6A solves is **research integrity in out-of-sample forward evaluation**:
1. **Look-Ahead Bias & Data Snooping:** Evaluating strategies repeatedly on the same historical data leads to severe selection bias and overfitted backtests.
2. **Provider Coupling:** The legacy system was coupled directly to MetaTrader 5 CSV files. Phase 6A introduces a provider-neutral protocol capable of abstracting institutional ECN feeds (LMAX, Dukascopy, Interactive Brokers) and deterministic offline fixtures.
3. **Tamper-Evident Storage:** Flat CSV files lack cryptographic integrity checks. Phase 6A establishes an immutable Apache Parquet vault with cryptographic SHA-256 manifests, append-only ingestion ledgers, and single-pass evaluation gates.

```
+---------------------------------------------------------------------------------------+
|                                    GOLDFLOW ARCHITECTURE                              |
+---------------------------------------------------------------------------------------+
|                                                                                       |
|   +--------------------------+                 +----------------------------------+   |
|   |  Market Data Providers   |                 |       Strategy Research          |   |
|   |  - MockDataIngestion     |                 |  - SMC v1 Frozen (1091fb06...)   |   |
|   |  - MT5 Live IPC          |                 |  - SMC MTF Experiment            |   |
|   |  - LMAX / Dukascopy ECN  |                 |  - ICT Engine (Independent)      |   |
|   +------------+-------------+                 +----------------+-----------------+   |
|                |                                                |                     |
|                v                                                v                     |
|   +--------------------------+                 +----------------------------------+   |
|   | Observation Validation   |                 | Evaluation Pre-Registration      |   |
|   |  - Strict UTC Timestamps |                 |  - Protocol Binding              |   |
|   |  - Crossed Quote Filter  |                 |  - Git Commit & Config Hash Lock |   |
|   |  - Deduplication         |                 |  - T_registration Boundary       |   |
|   +------------+-------------+                 +----------------+-----------------+   |
|                |                                                |                     |
|                v                                                v                     |
|   +--------------------------+                 +----------------------------------+   |
|   | Immutable Parquet Vault  |                 | Controlled Evaluation Gate       |   |
|   |  - Monthly Partitions    |                 |  - Pre-Evaluation Verification   |   |
|   |  - SHA-256 Manifests     |<----------------|  - Single-Pass Consumption Lock  |   |
|   |  - Ingestion Ledger      |                 |  - Cryptographic Receipts        |   |
|   +------------+-------------+                 +----------------------------------+   |
|                |                                                                      |
|                v                                                                      |
|   +--------------------------+                                                        |
|   | Deterministic M1 Builder |                                                        |
|   |  - [T, T+60s) Bars       |                                                        |
|   |  - Zero Gap Interpolation|                                                        |
|   +--------------------------+                                                        |
|                                                                                       |
+---------------------------------------------------------------------------------------+
```

---

## 2. Ingestion Pipeline & Provider-Neutral Interface

### 2.1 Abstract Protocol (`src/data/ingestion/base.py`)
All market data providers implement the `DataIngestionProvider` abstract protocol:

```python
class DataIngestionProvider(abc.ABC):
    @property
    @abc.abstractmethod
    def provider_name(self) -> str: ...

    @abc.abstractmethod
    def is_authenticated(self) -> bool: ...

    @abc.abstractmethod
    def fetch_historical_ticks(
        self, symbol: str, start_time: dt.datetime, end_time: dt.datetime
    ) -> Tuple[List[RawTickObservation], Dict[str, Any]]: ...

    @abc.abstractmethod
    def stream_incremental_ticks(
        self, symbol: str, max_ticks: Optional[int] = None
    ) -> Iterator[RawTickObservation]: ...

    @abc.abstractmethod
    def get_instrument_specification(self, symbol: str) -> Dict[str, Any]: ...
```

### 2.2 Standardized Data Models (`src/data/ingestion/models.py`)
- `RawTickObservation`: Immutable dataclass representing a tick quote (`timestamp_utc`, `symbol`, `bid`, `ask`, `volume`, `sequence_id`, `provider`, `flags`). Automatically localizes or converts timestamps to UTC. Properties `spread`, `mid`, and `is_crossed` provide zero-cost derived metrics.
- `AggregatedBar`: Standardized candlestick bar covering $[T, T+\Delta t)$ with explicit spread distribution metrics (`spread_open`, `spread_close`, `spread_min`, `spread_max`, `spread_mean`), tick count, and `is_incomplete` flag.
- `IngestionBatchMetadata`: Structured audit record capturing total ticks, valid/rejected counts, rejection reasons, partition file path, and partition SHA-256 hash.

### 2.3 Deterministic Mock Feed (`src/data/ingestion/mock_provider.py`)
Provides offline, reproducible data generation without network access or third-party credentials:
- Seedable pseudo-random generator simulating gold price paths around \$2,650/oz with typical 15–35 cent spreads.
- Anomaly injection suite for stress-testing:
  - `inject_crossed_quotes`: Artificially forces `bid > ask` with negative spreads.
  - `inject_invalid_prices`: Injects negative prices or extreme outliers (\$999,999).
  - `inject_duplicates`: Emits duplicate ticks with identical timestamps.
  - `inject_out_of_order`: Inverts adjacent tick timestamps.
  - `simulate_auth_failure` / `simulate_rate_limit`: Validates exception handling.

---

## 3. Observation Validation & Timestamp Canonicalization

Implemented in `src/data/ingestion/validator.py`:

1. **Strict UTC Canonicalization:** All incoming timestamps are parsed with `format="ISO8601"` and converted to UTC-aware `pd.Timestamp`.
2. **Chronological Sorting:** If timestamps are not monotonically increasing, the pipeline logs out-of-order inversions and re-sorts chronologically with stable secondary ordering on `sequence_id`.
3. **Crossed Quotes Filtering:** Quotes where $bid > ask$ (or spread $< 0$) are rejected and logged to prevent distorted entry/exit execution.
4. **Physical Gold Price Bounds:** Prices outside the plausible range (\$500.0 to \$10,000.0/oz) are dropped as corrupted data feed artifacts.
5. **Spread Bounds:** Spreads exceeding \$50.0/oz are filtered out as anomalous illiquidity spikes.
6. **Deduplication:** Ticks with identical timestamps, prices, and volumes are purged, logging duplicate indices.
7. **Traceability:** Emits a `ValidationAuditReport` detailing valid counts, dropped counts, rejection categories, and individual log records.

---

## 4. Immutable Parquet Vault & Manifest Management

Implemented in `src/vault/raw_storage.py`:

### 4.1 Storage Format & Partitioning Scheme
- Format: **Apache Parquet (pyarrow)** with `SNAPPY` compression and version 2.6 metadata. Columnar storage reduces disk usage by 75–85% compared to raw CSV and accelerates timestamp-range scanning.
- Partition Path:
  `{vault_root}/raw_vault/{symbol}/{year}/{symbol}_{provider}_{year}{month:02d}.parquet`
- Daily partitions are optionally supported: `{symbol}_{provider}_{year}{month:02d}{day:02d}.parquet`.

### 4.2 Cryptographic Manifests (`.manifest.json`)
Every partition file is accompanied by a cryptographic manifest:
```json
{
  "format_version": "1.0",
  "file_name": "XAUUSD_MOCK_ECN_202610.parquet",
  "partition_relative_path": "raw_vault/XAUUSD/2026/XAUUSD_MOCK_ECN_202610.parquet",
  "file_sha256": "3e9b1d7f...",
  "row_count": 500000,
  "start_time_utc": "2026-10-01T00:00:00.125000Z",
  "end_time_utc": "2026-10-31T23:59:58.850000Z",
  "symbol": "XAUUSD",
  "provider": "MOCK_ECN",
  "columns": ["timestamp_utc", "symbol", "bid", "ask", "spread", "mid", "volume", "sequence_id", "provider"],
  "file_size_bytes": 14582910,
  "created_at_utc": "2026-10-28T19:45:00Z"
}
```

### 4.3 Atomic Writing & Ingestion Ledger
- **Atomic Writes:** Partitions are written to temporary files (`tempfile.mkstemp`) within the target directory and swapped into place using `os.replace`. If any failure occurs, the existing partition is never corrupted.
- **Ingestion History Ledger:** Every partition commitment appends an immutable JSON record to `{vault_root}/manifests/ingestion_history.jsonl`.
- **Resumable State Checkpoints:** `{vault_root}/raw_vault/{symbol}/checkpoint.json` tracks the latest committed UTC timestamp and partition file to permit resuming interrupted downloads.

---

## 5. Holdout Vault Physical Segregation & Windows Threat Model

Implemented in `src/vault/holdout.py`:

### 5.1 Physical Directory Hierarchy
The vault directory is configured via the environment variable `GOLDFLOW_VAULT_STORAGE_PATH` (defaults to `./goldflow_vault`):

```
{vault_root}/
  ├── development/        # Unrestricted scratchpad, backtest caches, ad-hoc runs
  ├── raw_vault/          # Canonical raw tick/bar Parquet partitions
  ├── holdout_vault/      # Sealed, read-only datasets reserved for forward evaluation
  ├── manifests/          # Cryptographic manifests and append-only audit ledgers
  │     ├── ingestion_history.jsonl
  │     └── holdout_access_audit.log
  └── evaluations/        # Pre-registration files and evaluation receipts
```

### 5.2 Access Control & Windows Read-Only Attributes
- Sealing datasets via `HoldoutVaultManager.seal_dataset()` applies both:
  1. Standard Python read-only file permissions: `os.chmod(p, current_mode & ~stat.S_IWRITE)`.
  2. Windows OS-level read-only attribute: `attrib +r <file>`.
- Audit Logging: All access (sealing, verification, forward evaluation) appends structured JSON entries to `holdout_access_audit.log` capturing caller, registration ID, dataset path, timestamp, and purpose.

### 5.3 Threat Model & Security Boundaries
- **Single-User / Local Admin Boundary:** In a single-user Windows workstation environment, a process running with the researcher's local administrator privileges possesses the technical capability to strip read-only attributes (`attrib -r`) or delete files. GoldFlow does not rely on unrealistic claims of hardware security module (HSM) immutability on local commodity drives.
- **Cryptographic Tamper-Evidence:** GoldFlow enforces integrity mathematically:
  1. All partitions and sealed holdouts have SHA-256 digests recorded in manifests and mirrored in registration records.
  2. If any byte in a Parquet file is altered, `verify_partition()` and `verify_holdout_integrity()` immediately detect hash divergence and abort execution.
  3. Pre-registration records lock the strategy's git commit and frozen configuration SHA-256 digest prior to holdout evaluation.
- **Enterprise Multi-User Guidance (NTFS ACLs):** For institutional deployment across separate service accounts, permissions can be locked at the OS level:
  ```powershell
  icacls "C:\goldflow_vault\holdout_vault" /inheritance:r /grant:r "SYSTEM":(OI)(CI)F "GoldFlow_Evaluator":(OI)(CI)R
  ```

---

## 6. Pre-Registration Protocol & Single-Pass Evaluation Gate

Implemented in `src/vault/registration.py` and `src/vault/evaluation_gate.py`:

### 6.1 Registration Artifacts
Before any evaluation against sealed holdout data can proceed, an immutable pre-registration record must be created:
1. **Strategy Identity:** Strategy name (e.g., `SMC_v1_frozen`).
2. **Frozen Config SHA-256 Digest:** Strictly checked against `configs/smc_v1_frozen.json` (must equal `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`).
3. **Git Commit:** Current HEAD commit hash.
4. **Evaluation Type:**
   - `FORWARD_TEMPORAL`: Evaluates future data collected after registration timestamp $T_{\text{registration}}$.
   - `CROSS_PROVIDER`: Evaluates contemporaneously observed data from an independent secondary broker/ECN.
5. **Start Boundary $T_{\text{registration}}$:** Strict temporal boundary in UTC.

The registration is saved to both `configs/registered_evaluations/{registration_id}.json` and `{vault_root}/evaluations/{registration_id}.json` and locked as read-only.

### 6.2 Controlled Gate Execution & Single-Pass Consumption
When `EvaluationGate.execute_evaluation()` is called:
1. **Pre-Evaluation Gate Checks:**
   - Verifies registration exists and is in `REGISTERED` status.
   - If status is `EVALUATED_CONSUMED`, raises `EvaluationGateError` ("MULTIPLE TESTING REJECTED: Registration has already been evaluated and consumed").
   - Verifies current `configs/smc_v1_frozen.json` hash matches registered hash.
   - Verifies target dataset SHA-256 matches registered manifest digest.
   - **Temporal Boundary Enforcement:** If `FORWARD_TEMPORAL`, verifies that no observation in the dataset has a timestamp prior to $T_{\text{registration}}$. If earlier data is detected, raises `EvaluationGateError` ("LOOK-AHEAD / TEMPORAL CONTAMINATION DETECTED").
2. **Audited Execution:** Logs access event to `holdout_access_audit.log` with registration ID.
3. **Single-Pass Consumption Lock:** Immediately updates registration status to `EVALUATED_CONSUMED` in both locations and re-applies read-only locks.
4. **Cryptographic Receipt:** Emits `{vault_root}/evaluations/RECEIPT_{registration_id}.json` containing execution metrics, dataset SHA-256 digests, and completion timestamp.

---

## 7. Deterministic M1 Bar Synthesis

Implemented in `src/data/ingestion/bar_builder.py`:

- **Interval Boundary Standard:** Adheres strictly to the $[T, T+60\text{s})$ left-closed, right-open convention:
  $$\text{Bar Timestamp } T = \lfloor t_{\text{tick}} \rfloor_{\text{1 minute}}$$
- **Aggregation Logic:**
  - $Open$: First tick price in $[T, T+60\text{s})$.
  - $High$: Maximum tick price in $[T, T+60\text{s})$.
  - $Low$: Minimum tick price in $[T, T+60\text{s})$.
  - $Close$: Last tick price in $[T, T+60\text{s})$.
  - $TickVolume$: Total count of ticks in interval.
  - $RealVolume$: Sum of tick volumes.
  - $SpreadMetrics$: Calculates $Spread_{open}, Spread_{close}, Spread_{min}, Spread_{max}, Spread_{mean}$.
- **Zero Gap Interpolation:** **Crucially, the synthesizer never creates synthetic candles during market closures, weekend gaps, or data pauses.** Only intervals containing actual tick observations generate bars.
- **Incomplete Bar Detection:** Trailing bars that are still forming or truncated can be flagged with `is_incomplete = True` or excluded via `exclude_incomplete_trailing_bar = True`.

