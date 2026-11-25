# GOLDFLOW — PHASE 6I: STAGE A
## Dukascopy BI5 Decoder & Price-Scale Offline Audit Report

**Date:** 2026-10-30  
**Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Object Format:** `sha1`  
**Author:** Quantitative Architecture & Security Audit Team  
**Scope:** Offline inspection of BI5 binary unpacking, price scaling invariants, network boundaries, and storage manifests.

---

## 1. Executive Summary

A rigorous forensic audit of the GoldFlow market data ingestion subsystem was conducted across:
- `src/data/ingestion/bi5_decoder.py` (BI5 binary LZMA decompressor and record parser)
- `src/data/ingestion/instrument_spec.py` (Instrument specification catalog and fail-closed gates)
- `src/data/ingestion/dukascopy_provider.py` (Provider adapter and retrieval pilot)
- `src/vault/raw_storage.py` (Partition storage manager and immutable object vault)

### Audit Verdict: **SECURE & FAIL-CLOSED**
1. **Binary Unpacking:** Struct format `>3I2f` (20 bytes per record) is mathematically sound and strictly enforced with zero allowable trailing bytes (`decomp_len % 20 == 0`).
2. **Price-Scale Vulnerability Mitigated:** Dukascopy's historical gold feed convention uses `price_scale = 1000.0`. While standard among open-source JForex parsers, it remains unconfirmed by bank SLA. The system correctly classifies `DUKASCOPY_XAUUSD_SPEC` as `UNVERIFIED_PENDING_CONFIRMATION` and enforces an unconditional fail-closed gate for real network ingestion.
3. **Network Boundary:** External network access is disabled by default (`allow_network=False`). Bounded retrieval pilot raises `IngestionError` before socket creation.
4. **Storage Isolation:** Partition writes enforce strict boundary checks preventing writes into holdout vaults.

---

## 2. Low-Level Binary Record Specification

### 2.1 Struct Layout (`>3I2f`)
Dukascopy `.bi5` archives store tick observations in 20-byte binary records packed in big-endian network byte order (`>3I2f` / `>IIIff`):

| Field Index | Field Name | Data Type | Size (Bytes) | Binary Representation | Description |
|:---:|:---|:---:|:---:|:---|:---|
| 0 | `offset_ms` | `uint32` | 4 | Big-endian unsigned 32-bit int | Milliseconds offset from UTC partition base |
| 1 | `raw_ask` | `uint32` | 4 | Big-endian unsigned 32-bit int | Unscaled integer Ask price |
| 2 | `raw_bid` | `uint32` | 4 | Big-endian unsigned 32-bit int | Unscaled integer Bid price |
| 3 | `ask_vol` | `float32` | 4 | IEEE 754 single-precision float | Ask liquidity / volume (contracts/lots) |
| 4 | `bid_vol` | `float32` | 4 | IEEE 754 single-precision float | Bid liquidity / volume (contracts/lots) |
| **Total** | | | **20** | | Fixed record size |

### 2.2 Invariant Checks Implemented in `DukascopyBi5Decoder`
1. **Decompression Integrity:** LZMA decompression is wrapped in strict exception handling (`DecompressionError`).
2. **Payload Length Validation:** Any decompressed payload whose byte length is not an exact multiple of 20 (`decomp_len % 20 != 0`) raises `InvalidPayloadLengthError`. No trailing bytes or truncated records are silently ignored.
3. **Timestamp Offset Range:**
   - Hourly partition: `0 <= offset_ms < 3,600,000` (1 hour in ms).
   - Daily partition: `0 <= offset_ms < 86,400,000` (24 hours in ms).
   - Out-of-bounds offsets are recorded and rejected (`INVALID_TIMESTAMP_OFFSET`).
4. **Volume Invariants:** Must be finite IEEE 754 floats and non-negative (`ask_vol >= 0`, `bid_vol >= 0`). Inf/NaN/negative values are rejected.
5. **Price Invariants:** Raw integer prices must be strictly positive (`raw_ask > 0`, `raw_bid > 0`).
6. **Crossed Quote Rejection:** De-scaled Bid price must not exceed Ask price (`bid_price <= ask_price`). Crossed quotes (`bid > ask`) are dropped and logged (`CROSSED_QUOTE`).
7. **Duplicate Event Deduplication:** Deduplication uses a full tuple fingerprint `(offset_ms, raw_ask, raw_bid, round(ask_vol, 5), round(bid_vol, 5))`. Identical tick bursts are deduplicated while legitimate microsecond multi-fill orders with distinct volumes/prices are preserved.

---

## 3. Price-Scale Analysis & Vulnerability Assessment

### 3.1 Scaling Mechanics
In `src/data/ingestion/bi5_decoder.py`:
```python
ask_price = round(raw_ask / price_scale, digits)
bid_price = round(raw_bid / price_scale, digits)
```

For major Forex currency pairs (e.g., EUR/USD), Dukascopy uses `price_scale = 100000.0` (5 decimal digits, where integer `108500` = `1.08500`). This is officially documented in Dukascopy JForex specifications.

For XAUUSD (Gold bullion), historical community parsers divide raw integers by `1000.0` (`digits = 3`), where integer `4156940` represents `$4,156.940`.

### 3.2 The Uncalibrated Assumption Risk
| Potential Scale | Raw Integer | Decoded Gold Price | Impact on Strategy |
|:---:|:---:|:---:|:---|
| `100.0` | `4156940` | `$41,569.40` | 10x price distortion; total strategy breakdown |
| **`1000.0`** (Assumed) | `4156940` | **`$4,156.94`** | **True spot bullion dollar valuation** |
| `10000.0` | `4156940` | `$415.69` | 0.1x price distortion; position sizing catastrophe |
| `100000.0` (FX Standard) | `4156940` | `$41.57` | 0.01x price distortion; complete margin exhaustion |

**Vulnerability:** If GoldFlow were to adopt `price_scale = 1000.0` for real network ingestion without cryptographic empirical verification against an authoritative reference quote, an error of $10\times$ or $100\times$ could silently corrupt:
- Stop Loss distance calculations (ruining R-multiple calculations).
- Order block and FVG threshold evaluations.
- Spread drag and transaction cost models.
- Power BI risk metrics.

### 3.3 Two-Tier Fail-Closed Gate Implementation
In `src/data/ingestion/instrument_spec.py`:
1. `validate_for_decoding(allow_unverified=False)`:
   - Used for local synthetic test fixtures (`SYNTHETIC_FIXTURE_ONLY` or testing).
   - If `allow_unverified=False` and status is not `VERIFIED`, raises `UnverifiedPriceScaleError`.
2. `validate_for_real_network_ingestion()`:
   - **Unconditional Fail-Closed Gate.**
   - Does **NOT** accept any `allow_unverified` parameter.
   - Rejects any specification whose `verification_status != VerificationStatus.VERIFIED`.
   - Rejects `SYNTHETIC_FIXTURE_ONLY` outright.
   - Enforced directly inside `DukascopyIngestionProvider.execute_bounded_retrieval_pilot()`.

```python
# From src/data/ingestion/dukascopy_provider.py lines 245-247:
spec = get_provider_instrument_spec(self.provider_name, symbol)
spec.validate_for_real_network_ingestion()  # NO override accepted!
```

Because `DUKASCOPY_XAUUSD_SPEC.verification_status` is `VerificationStatus.UNVERIFIED_PENDING_CONFIRMATION`, any attempt to retrieve real XAUUSD network data raises:
```text
UnverifiedPriceScaleError: UNRESOLVED PREREQUISITE: REAL NETWORK INGESTION BLOCKED:
Instrument DUKASCOPY:XAU/USD has verification status 'UNVERIFIED_PENDING_CONFIRMATION' (requires VERIFIED).
```

---

## 4. Network Boundary & Provider URL Construction

### 4.1 URL Construction Invariant
Dukascopy public CDN paths follow the convention:
```
https://datafeed.dukascopy.com/datafeed/{PROVIDER_SYMBOL}/{YYYY}/{MM_ZERO_INDEXED:02d}/{DD:02d}/{HH:02d}h_ticks.bi5
```
**Critical Invariant:** Month `MM` is **0-indexed** in Dukascopy's directory tree:
- January = `00`
- October = `09`
- December = `11`

In `bi5_decoder.py`:
```python
month = int(m_hourly.group("month")) + 1  # Successfully converts 0-indexed month back to 1-12
```
In `dukascopy_provider.py`:
```python
zero_month = hour_ts.month - 1  # Correctly formats month for CDN request
url = f"{DUKASCOPY_PUBLIC_CDN_BASE}/{prov_sym}/{hour_ts.year:04d}/{zero_month:02d}/{hour_ts.day:02d}/{hour_ts.hour:02d}h_ticks.bi5"
```

### 4.2 Network Guard Enforcement
`execute_bounded_retrieval_pilot` requires `allow_network=True`. By default, `allow_network=False`, raising:
```text
IngestionError: NETWORK_PILOT_DISABLED: Network retrieval requires explicit operator activation (allow_network=True).
```
Additionally, redirect checks ensure requests cannot be hijacked to unauthorized external domains.

---

## 5. Storage & Partition Immutability

### 5.1 Storage Architecture
The storage layout in `PartitionStorageManager` enforces:
1. **Raw Source Persistence:** Compressed `.bi5` bytes are hashed with SHA-256 and written to `data/vault/sources/{provider}/{symbol}/{year}/` before decoding.
2. **Partition Parquet:** Decoded observations are saved in partitioned Parquet files with explicit UTC timestamp columns.
3. **Cryptographic Manifest:** Every partition write generates a JSON manifest containing `file_sha256`, `record_count`, `source_object_path`, and `provider`.
4. **Holdout Directory Rejection:** Attempts to specify an output directory containing `"holdout"` fail closed immediately.

---

## 6. Audit Conclusion & Recommendations

| Control | Status | Evidence |
|:---|:---:|:---|
| 20-byte record unpacking | PASSED | Struct `>3I2f`, exact modulo 20 byte check |
| Timestamp normalization | PASSED | Strict UTC base timestamp + millisecond delta |
| Price-scale verification gate | PASSED | `validate_for_real_network_ingestion()` fails closed unconditionally |
| Network pilot isolation | PASSED | `allow_network=False` fails closed before socket creation |
| Storage boundaries | PASSED | Holdout path traversal rejected, raw source hashed before decoding |

**Recommendation for Stage B:**
Proceed with calibration protocol design. Identify a specific historical hour where authoritative tick/bar data from MT5 is already verified on disk, define exact tolerance bounds ($\pm \$0.50$), and prepare the operator authorization checkpoint.

