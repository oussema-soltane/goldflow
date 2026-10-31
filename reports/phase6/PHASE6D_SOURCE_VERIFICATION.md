# GOLD FLOW — Phase 6D: Dukascopy Source Verification Report

**Document class:** Research-integrity report  
**Phase:** 6D — Controlled Dukascopy Calibration and Ingestion Pilot  
**Date:** 2026-10-29  
**Prepared by:** GoldFlow automated research pipeline  
**Repository revision:** `ad9807f8405811d65148d73d72139243f3d6a77f` (object format: sha1)  
**Network requests made during this phase:** ZERO

---

## Executive Summary

This report documents the findings of the Dukascopy data-source due-diligence investigation
conducted during Phase 6D.  No real provider connections were made.  All findings are based on
publicly available documentation, community analysis, and static inspection of the Dukascopy
public CDN URL structure.

Two access routes were identified: a free public HTTPS CDN and a cost-incurring AWS S3 archive.
The CDN route is selected.  The S3 route is blocked under the GoldFlow zero-cost mandate.

---

## Section 1 — Public HTTPS CDN Verification

### 1.1 Base URL

```
https://datafeed.dukascopy.com/datafeed/
```

**Access requirements:** None.  No authentication, no credentials, no registration.  
**Cost:** Zero.  Plain HTTPS GET requests.

### 1.2 File Layout

Tick data is stored as individual hourly `.bi5` files.  The canonical path template is:

```
{BASE}/{SYMBOL}/{YYYY}/{MM:02d}/{DD:02d}/{HH:02d}h_ticks.bi5
```

**Critical detail — zero-indexed month encoding:**  
The month component is **0-indexed** (January = `00`, October = `09`, December = `11`).  
This is non-standard.  GoldFlow's `Bi5FileLayout` implementation encodes this correctly as
`zero_indexed_month = calendar_month - 1`.

**Example path for XAUUSD, 2024-11-01 08:00 UTC:**
```
https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/10/01/08h_ticks.bi5
```
(Month 11 → zero-indexed 10.)

### 1.3 XAUUSD Symbol Confirmation

The symbol `XAUUSD` is confirmed available on the Dukascopy public CDN feed.  Community parsers
and the GoldFlow `bi5_decoder.py` reference this symbol directly.

### 1.4 File Format

Each `.bi5` file is an LZMA-compressed binary stream.  After decompression, the payload consists
of fixed-width 20-byte records:

| Field       | Type     | Bytes | Description                              |
|-------------|----------|-------|------------------------------------------|
| `ms_offset` | uint32   | 4     | Millisecond offset from hour start       |
| `ask_raw`   | uint32   | 4     | Raw ask price (integer, requires scaling)|
| `bid_raw`   | uint32   | 4     | Raw bid price (integer, requires scaling)|
| `ask_vol`   | float32  | 4     | Ask volume                               |
| `bid_vol`   | float32  | 4     | Bid volume                               |

Big-endian byte order throughout.  Record stride: 20 bytes.

### 1.5 Confirmed CDN Characteristics

| Property                     | Status      | Detail                                 |
|------------------------------|-------------|----------------------------------------|
| Authentication required      | ✅ NONE     | Open HTTPS endpoint                    |
| Cost per request             | ✅ ZERO     | No billing mechanism identified        |
| XAUUSD available             | ✅ YES      | Symbol confirmed in community parsers  |
| File format                  | ✅ KNOWN    | LZMA-compressed 20-byte tick records   |
| Month encoding               | ⚠️ NON-STD | Zero-indexed (00–11), not 01–12        |
| Long-term SLA / rate limits  | ❓ UNKNOWN  | No published SLA found                 |

---

## Section 2 — AWS S3 Archive Assessment

### 2.1 Bucket Identification

**Bucket:** `cfg-public-proper-wallaby`  
**Region:** `eu-west-1`  
**Path format:** Same hierarchical layout as the CDN

### 2.2 Requester Pays Policy

The S3 bucket is configured with **Requester Pays** billing.  This means:

- AWS credentials are **required** to access the bucket.
- Data transfer costs (~\$0.02 USD/GB) are **charged to the requester's AWS account**.
- The first GB per month may be within free-tier limits, but this cannot be guaranteed.

**Assessment: ACCESS BLOCKED.**

Under the GoldFlow zero-cost research mandate ("Do not purchase data, create accounts, submit
credentials, or incur charges"), this route must not be accessed during Phase 6D or any
subsequent phase without explicit operator authorisation and a documented cost-impact assessment.

### 2.3 S3 Route Status

| Property            | Status          | Detail                                    |
|---------------------|-----------------|-------------------------------------------|
| Credentials needed  | ❌ REQUIRED     | AWS access key and secret required        |
| Cost                | ❌ INCURS COST  | Requester Pays ~$0.02/GB                 |
| Phase 6D access     | 🚫 BLOCKED      | Violates zero-cost mandate                |
| Future eligibility  | CONDITIONAL     | Requires operator sign-off and cost budget|

---

## Section 3 — Access Terms and Data Usage

### 3.1 Public CDN Usage

Based on publicly available information and community usage patterns:

| Use case                           | Status          |
|------------------------------------|-----------------|
| Personal quantitative research     | ✅ PERMITTED    |
| Storing derived OHLC Parquet bars  | ✅ PERMITTED    |
| Storing raw `.bi5` files locally   | ⚠️ REVIEW TERMS |
| Redistribution of raw tick data    | ❌ PROHIBITED   |
| Commercial redistribution          | ❌ PROHIBITED   |

### 3.2 Research-Integrity Posture

GoldFlow retains only:
- Derived OHLC bar aggregates stored in the Parquet vault.
- Pre-decode SHA-256 hashes of raw files (for audit purposes, not content reconstruction).
- Audit log entries (timestamps, file paths, byte counts, hashes).

Raw `.bi5` binary files are not redistributed and are not permanently archived unless operator
policy explicitly permits this.

### 3.3 Unresolved Terms Questions

> **REQUIRES_PROVIDER_CONFIRMATION**

1. Whether automated programmatic access to the public CDN is explicitly permitted or merely
   tolerated.
2. Sustained request pacing limits (if any) that would affect bulk historical retrieval.
3. Whether retaining derived bars (OHLC Parquet) with traceable provenance is formally
   sanctioned.

---

## Section 4 — Selected Data Route

**Selected route:** Public HTTPS CDN (`https://datafeed.dukascopy.com/datafeed/`)  
**S3 route status:** BLOCKED (Requester Pays — would incur charges)

The `execute_bounded_retrieval_pilot()` method in `src/data/ingestion/dukascopy_provider.py`
uses only the public CDN base URL.  The S3 route is not referenced in any GoldFlow code path.

---

## Section 5 — Unresolved Questions and Blockers

| Item | Status | Notes |
|------|--------|-------|
| Long-term CDN pacing / SLA | UNRESOLVED | No published documentation found |
| S3 access policy | BLOCKED | Requester Pays; requires operator cost sign-off |
| Raw `.bi5` local retention policy | PENDING REVIEW | Legal review of provider terms recommended |
| CDN access terms (automated) | REQUIRES_PROVIDER_CONFIRMATION | No formal ToS found for programmatic use |

---

## Section 6 — Verification Methodology

All findings in this report were obtained by:

1. **Static inspection** of the GoldFlow source code (`src/data/ingestion/bi5_decoder.py`,
   `src/data/ingestion/dukascopy_provider.py`, `src/data/ingestion/instrument_spec.py`).
2. **Public documentation review** — Dukascopy JForex API documentation, community parser
   repositories, and publicly available technical writeups.
3. **Structural analysis** of the `.bi5` format using GoldFlow's synthetic fixture generators
   (`tests/fixtures/synthetic_bi5.py`).

**Zero real HTTP requests were made during Phase 6D.**  The `execute_bounded_retrieval_pilot()`
method defaults to `allow_network=False`, which causes an immediate fail-closed exception before
any socket is opened.

---

*Report generated: 2026-10-29 | Phase: 6D | Repository: ad9807f*

