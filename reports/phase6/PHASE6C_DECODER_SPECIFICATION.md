# GoldFlow Phase 6C: Dukascopy BI5 Decoder & Instrument Specification

**Author:** Senior Quantitative Research Engineer & Financial Data Architect  
**Date:** 2026-10-28  
**Status:** Canonical Technical Specification  
**Decoder Version:** `1.0.0` (`BI5_DECODER_VERSION`)  
**Record Format:** 20-byte Big-Endian (`>3I2f` / `>IIIff`)  
**Primary Instrument:** XAUUSD (Gold Spot Bullion vs. US Dollar)  

---

## 1. Executive Technical Overview

The `.bi5` format is Dukascopy Bank SA's proprietary compressed binary format used to distribute historical tick-by-tick market data via its Swiss Forex (SWFX) Marketplace data feeds.

In GoldFlow Phase 6C, we implemented a provider-neutral, fail-closed decoder (`DukascopyBi5Decoder` in [bi5_decoder.py](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/src/data/ingestion/bi5_decoder.py)) that:
1. Decompresses raw LZMA byte streams using the standard library `lzma` module.
2. Enforces record boundary alignment on exactly 20-byte chunks.
3. Reconstructs millisecond-precision UTC timestamps based on explicit layout anchors.
4. Fails closed if asked to decode an instrument whose price scale has not been verified against an official SLA.
5. Captures raw file SHA-256 digests prior to decoding, ensuring complete auditability.

---

## 2. Binary Record Layout Specification

Once the raw LZMA stream is decompressed, the payload consists of a contiguous sequence of fixed **20-byte records**. Every record is structured in standard **Big-Endian** (`>`) network byte order:

| Byte Offset | Field Name | Data Type | Struct Format | Description |
| :--- | :--- | :--- | :--- | :--- |
| **00 – 03** | `time_offset_ms` | `uint32` (unsigned int) | `>I` | Milliseconds offset from the file's base UTC timestamp anchor |
| **04 – 07** | `raw_ask` | `uint32` (unsigned int) | `>I` | Unscaled integer representation of the Ask price |
| **08 – 11** | `raw_bid` | `uint32` (unsigned int) | `>I` | Unscaled integer representation of the Bid price |
| **12 – 15** | `ask_volume` | `float32` (single float) | `>f` | Ask liquidity volume (in millions/lots, raw provider units) |
| **16 – 19** | `bid_volume` | `float32` (single float) | `>f` | Bid liquidity volume (in millions/lots, raw provider units) |

The complete composite Python `struct` unpack format is:
```python
BI5_STRUCT_FORMAT = ">3I2f"  # Equivalent to ">IIIff"
```

### 2.1 Payload Length Integrity Rule
The decompressed byte length $L$ must be an exact integer multiple of 20:
$$L \pmod{20} == 0$$
If $L \pmod{20} \neq 0$, the payload is truncated or corrupted. The decoder raises `InvalidPayloadLengthError` and rejects the partition. Unexplained trailing bytes are strictly prohibited.

---

## 3. Timestamp Reconstruction & Layout Anchors

Dukascopy distributes `.bi5` tick data across two distinct layout structures. The decoder supports both explicitly via the `Bi5FileLayout` enum:

### 3.1 Layout 1: Hourly Files (`Bi5FileLayout.HOURLY`)
- **Base Anchor:** UTC hour boundary (`YYYY-MM-DD HH:00:00.000 UTC`).
- **Offset Bounds:** $0 \le \Delta t_{\text{ms}} < 3\,600\,000$ ms.
- **Timestamp Formula:**
  $$T_{\text{utc}} = T_{\text{hour\_base}} + \Delta t_{\text{ms}}$$
- **Path Pattern:**
  `datafeed/SYMBOL/YYYY/MM/DD/HHh_ticks.bi5`
- **Critical Zero-Indexed Month Rule:** In Dukascopy CDN directory paths, the month `MM` is **0-indexed** (`00` = January, `09` = October, `11` = December). The decoder automatically normalizes `MM` by adding 1:
  $$\text{Calendar Month} = \text{int}(MM) + 1$$

### 3.2 Layout 2: Daily Files (`Bi5FileLayout.DAILY`)
- **Base Anchor:** UTC day boundary (`YYYY-MM-DD 00:00:00.000 UTC`).
- **Offset Bounds:** $0 \le \Delta t_{\text{ms}} < 86\,400\,000$ ms.
- **Timestamp Formula:**
  $$T_{\text{utc}} = T_{\text{day\_base}} + \Delta t_{\text{ms}}$$
- **Path Pattern:**
  `datafeed/SYMBOL/YYYY/MM/DD_ticks.bi5`

### 3.3 Layout Ambiguity Invariant
The decoder **does not guess** or heuristically infer file layout based on whether timestamps "look plausible". If the file path does not conform to a recognized pattern and the caller does not supply an explicit `Bi5FileLayout`, decoding fails immediately with `AmbiguousLayoutError`.

---

## 4. Price Scaling & Fail-Closed Specification

Raw integer prices are converted to floating-point units using an explicit scale factor:
$$P_{\text{float}} = \text{round}\left(\frac{P_{\text{raw}}}{\text{price\_scale}}, \text{digits}\right)$$

### 4.1 The XAUUSD Price Scaling Hazard
In community parsers, XAUUSD is commonly divided by `1000.0` (e.g. integer `2735250` $\to$ \$2,735.250/oz). However, this scale has **not yet been corroborated by an official Dukascopy SLA or contract specification**.

To protect research integrity, GoldFlow implements the `ProviderInstrumentSpec` architecture ([instrument_spec.py](file:///c:/Users/ousse/Downloads/GoldFlow_Ultimate_Updated/GoldFlow_SMC_Primary_Updated/src/data/ingestion/instrument_spec.py)):
- **Status Enum:**
  - `VERIFIED`: Formally confirmed by official documentation (e.g. `EUR/USD` with scale `100000.0`).
  - `UNVERIFIED_PENDING_CONFIRMATION`: Community convention not yet certified by official SLA (e.g. `XAU/USD` with proposed scale `1000.0`).
  - `SYNTHETIC_FIXTURE_ONLY`: Explicitly labeled synthetic test fixture.

### 4.2 Fail-Closed Enforcement
When attempting to decode real provider data with an unverified specification, `DukascopyBi5Decoder` raises:
```python
UnverifiedPriceScaleError: "UNRESOLVED PREREQUISITE: Price scale 1000.0 for DUKASCOPY:XAU/USD is marked as 'UNVERIFIED_PENDING_CONFIRMATION' (not VERIFIED)..."
```
To run tests on synthetic fixtures, callers must explicitly declare `allow_unverified_scale=True`. Real-provider ingestion cannot proceed until official calibration or confirmation is obtained.

---

## 5. Record-Level Validation Rules

Each 20-byte record is evaluated against data quality rules before acceptance:

1. **Timestamp Offset Bounds:**
   - Hourly files: $\Delta t_{\text{ms}} \in [0, 3\,600\,000)$.
   - Daily files: $\Delta t_{\text{ms}} \in [0, 86\,400\,000)$.
   - Violations are dropped and recorded as `INVALID_TIMESTAMP_OFFSET`.
2. **Finite & Non-Negative Volumes:**
   - $\text{math.isfinite}(\text{ask\_vol}) \land \text{math.isfinite}(\text{bid\_vol})$.
   - $\text{ask\_vol} \ge 0.0 \land \text{bid\_vol} \ge 0.0$.
   - Violations are dropped and recorded as `NON_FINITE_OR_NEGATIVE_VOLUME`.
3. **Strictly Positive Raw Prices:**
   - $P_{\text{ask, raw}} > 0 \land P_{\text{bid, raw}} > 0$.
   - Non-positive prices are dropped as `NON_POSITIVE_RAW_PRICE`.
4. **Crossed Quotes Detection:**
   - If $P_{\text{bid}} > P_{\text{ask}}$, the quote is dropped as `CROSSED_QUOTE`.
5. **Duplicate Observations:**
   - Consecutive records having identical timestamp, bid, ask, and volumes are deduplicated.
6. **No Reinterpretation of Volumes:**
   - Raw floating-point volume fields are preserved as top-of-book volume in millions/lots. They are **never reinterpreted as exchange-traded contracts** without supporting clearinghouse evidence.
7. **Sequence Identifiers:**
   - Dukascopy does not transmit matching-engine sequence numbers. The decoder sets `sequence_id=None` rather than fabricating synthetic sequence IDs.

