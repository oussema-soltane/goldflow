# GOLDFLOW — PHASE 6I: STAGE B
## XAUUSD Price-Scale Calibration Protocol

**Date:** 2026-10-30  
**Git HEAD:** `ad9807f8405811d65148d73d72139243f3d6a77f`  
**Object Format:** `sha1`  
**Target Symbol:** `XAUUSD` (Spot Gold vs US Dollar)  
**Provider:** Dukascopy Bank SA (SWFX Marketplace)  
**Status:** PROTOCOL SPECIFICATION — READY FOR OPERATOR AUTHORIZATION

---

## 1. Purpose and Objective

The objective of this calibration protocol is to empirically verify the exact price-scale divisor for Dukascopy Bank's historical XAUUSD binary tick feed (`.bi5`), resolving the uncalibrated assumption in `DUKASCOPY_XAUUSD_SPEC` (`price_scale = 1000.0`).

Before any large-scale historical tick ingestion can be authorized, a single, precisely bounded historical partition will be retrieved from the zero-cost public CDN, decoded using candidate divisors, and compared against an authoritative, independently verified reference quote.

---

## 2. Reference Observation Selection

### 2.1 Target Calibration Window
- **Date:** `2026-10-15` (Thursday — active, highly liquid market session)
- **Hour:** `10:00:00 UTC` to `10:59:59.999 UTC` (London / European morning liquidity window)
- **Timezone:** Strictly `UTC` (zero offset)

### 2.2 Independent Reference Ground Truth
The ground-truth reference dataset is extracted from the institutional MetaTrader 5 broker terminal feed stored in `data/processed/XAUUSD_H1_clean.csv` and cross-validated against 12 consecutive 5-minute bars in `data/processed/XAUUSD_M5_clean.csv`.

#### Authoritative Reference Bar Profile (`2026-10-15 10:00:00+00:00`):
| Metric | Reference Value | Source |
|:---|:---:|:---|
| **Timestamp (UTC)** | `2026-10-15 10:00:00+00:00` | `XAUUSD_H1_clean.csv` (row 9929) |
| **Open Price** | **`$4,156.94`** | Initial trade of the 10:00 UTC hour |
| **High Price** | **`$4,158.80`** | Hourly peak (recorded at 10:05 UTC bar) |
| **Low Price** | **`$4,151.71`** | Hourly trough (recorded at 10:45 UTC bar) |
| **Close Price** | **`$4,154.76`** | Final trade of the 10:00 UTC hour |
| **Tick Volume** | **10,903** | Total broker tick count (sum of 12 M5 bars) |
| **Typical Spread** | **9 points ($0.09)** | Average institutional spread |

---

## 3. Dukascopy Feed Retrieval Specification

### 3.1 Canonical Endpoint URL
Dukascopy public CDN uses 0-indexed months (October = `09`).
- **Base Endpoint:** `https://datafeed.dukascopy.com/datafeed`
- **Symbol:** `XAUUSD`
- **Year:** `2026`
- **Month:** `09` (0-indexed for month 10, October)
- **Day:** `15`
- **Hour:** `10`
- **Canonical URL:**
  ```text
  https://datafeed.dukascopy.com/datafeed/XAUUSD/2026/09/15/10h_ticks.bi5
  ```

### 3.2 Network Guard and Limits
- **HTTP Method:** `GET`
- **Max Response Size:** 50 MB (expected raw `.bi5` is ~50 KB to 500 KB)
- **Timeout:** 10.0 seconds
- **Retry Strategy:** Max 3 retries with exponential backoff on HTTP 5xx
- **Network Gate:** Requires explicit parameter `allow_network=True`
- **Output Vault:** `data/vault/dukascopy/calibration/` (isolated from test holdouts)

---

## 4. Empirical Price-Scale Discrimination

### 4.1 Expected Raw Binary Values
When unpacked with struct `>3I2f`, the raw integer prices `raw_ask` and `raw_bid` are expected to be approximately `4,156,940` at the start of the hour.

### 4.2 Candidate Divisor Comparison
| Candidate Divisor | Tested Formula | Resulting Price | Divergence from MT5 Open ($4,156.94) | Discrimination Outcome |
|:---:|:---:|:---:|:---:|:---:|
| `100.0` (Cents) | `4156940 / 100.0` | `$41,569.40` | +$37,412.46 ($+900\%$) | **REJECTED (10x error)** |
| **`1000.0` (Target)** | `4156940 / 1000.0` | **`$4,156.94`** | **$\le \$0.50$ ($<0.01\%$)** | **CANDIDATE PASS** |
| `10000.0` | `4156940 / 10000.0` | `$415.69` | -$3,741.25 ($-90\%$) | **REJECTED (0.1x error)** |
| `100000.0` (FX Standard) | `4156940 / 100000.0` | `$41.57` | -$4,115.37 ($-99\%$) | **REJECTED (0.01x error)** |

Because each candidate scale differs by an entire order of magnitude ($10\times$), there is zero possibility of ambiguous classification.

---

## 5. Acceptance Tolerances & Verification Criteria

To certify `price_scale = 1000.0` as `VERIFIED`, the decoded hourly partition must satisfy all of the following criteria simultaneously:

### 5.1 Pricing Alignment Criteria
1. **Open Price Tolerance:**
   $$|P_{\text{dukascopy, first\_bid}} - 4156.94| \le \$0.50$$
   *(Accounts for inter-dealer bid/ask spread and cross-broker ECN dispersion).*
2. **High Price Tolerance:**
   $$|P_{\text{dukascopy, max\_ask}} - 4158.80| \le \$1.00$$
3. **Low Price Tolerance:**
   $$|P_{\text{dukascopy, min\_bid}} - 4151.71| \le \$1.00$$
4. **Close Price Tolerance:**
   $$|P_{\text{dukascopy, last\_bid}} - 4154.76| \le \$0.50$$

### 5.2 Microstructural Invariants
1. **Spread Sanity:** Median spread must be strictly positive and between $\$0.05$ and $\$0.50$ (5 to 50 points).
2. **Crossed Quotes:** Exactly $0$ crossed quotes (`bid > ask`).
3. **Tick Density:** Decompressed observation count $N \ge 1,000$ ticks (liquid London morning session).
4. **Volume Values:** All volume floats must be finite and $\ge 0$.

### 5.3 Cryptographic Integrity
1. **Source Hash:** SHA-256 of raw `.bi5` bytes recorded in manifest.
2. **Partition Hash:** SHA-256 of resulting Parquet file recorded in manifest.

---

## 6. Promotion & Authorization Workflow

```
[ Operator Authorization Granted ]
               │
               ▼
[ Single-Hour Retrieval Pilot (allow_network=True) ]
               │
               ▼
[ Compute Raw SHA-256 & Decompress LZMA ]
               │
               ▼
[ Verify Record Format (>3I2f, decomp_len % 20 == 0) ]
               │
               ▼
[ Evaluate Tolerances (|P - P_ref| <= $0.50) ]
       │                               │
       ├─ Fails ───────────────────────┼─ Passes
       ▼                               ▼
[ ABORT & Log Error ]           [ Update instrument_spec.py ]
                                [ status = VERIFIED ]
                                [ verified_date = "2026-10-30" ]
                                       │
                                       ▼
                                [ Authorize Phase 6J Acquisition ]
```

---

## 7. Execution Readiness

The test suite `tests/test_phase6i_calibration_readiness.py` implements synthetic mock tests of the exact comparison logic, ensuring that calibration execution will proceed deterministically upon operator clearance.

