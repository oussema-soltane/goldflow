# GOLD FLOW — Phase 6D: XAUUSD Price Scale Calibration Report

**Document class:** Research-integrity report  
**Phase:** 6D — Controlled Dukascopy Calibration and Ingestion Pilot  
**Date:** 2026-10-29  
**Prepared by:** GoldFlow automated research pipeline  
**Repository revision:** `ad9807f8405811d65148d73d72139243f3d6a77f` (object format: sha1)  
**Instrument:** XAU/USD (Gold vs US Dollar) on Dukascopy SWFX Marketplace  
**Calibration decision:** UNVERIFIED — real XAUUSD ingestion BLOCKED

---

## Executive Summary

This report documents the price-scale calibration investigation for XAUUSD raw integer values in
Dukascopy `.bi5` tick files.

Two conflicting conventions were identified in public sources.  The discrepancy could not be
resolved without comparing raw `.bi5` integer values against a ground-truth market reference at
a known UTC timestamp — an operation that requires network access and falls outside the Phase 6D
zero-network mandate.

**Decision: `DUKASCOPY_XAUUSD_SPEC` remains `UNVERIFIED_PENDING_CONFIRMATION`.**  
**Real XAUUSD ingestion is blocked until calibration evidence is produced.**

---

## Section 1 — Instrument Specification

| Property             | Value                           |
|----------------------|---------------------------------|
| Symbol               | `XAUUSD`                        |
| Provider             | Dukascopy Bank SA               |
| Marketplace          | SWFX (Swiss Forex Marketplace)  |
| Asset class          | Precious metals / spot FX       |
| Price unit           | USD per troy ounce              |
| Tick file format     | `.bi5` (LZMA-compressed binary) |
| Record layout        | 20-byte: ms_offset, ask, bid, ask_vol, bid_vol (big-endian) |

---

## Section 2 — The Price Scale Problem

### 2.1 What "price scale" means

In Dukascopy `.bi5` files, raw ask/bid prices are stored as **unsigned 32-bit integers**.  These
must be divided by a scaling factor to recover the actual price in USD.

For example, if the raw integer value is `2735125` and the scale is `1000.0`, the decoded price
is `$2735.125/oz`.  If the scale is `100.0`, the decoded price would be `$27351.25/oz` — which
is clearly wrong for gold at current market levels.

### 2.2 Proposed scale — community convention

Community parsers (JForex community scripts, GitHub repositories) commonly apply a scale of
**1000.0** for XAUUSD.

Example community interpretation:
```
raw_integer 2735125 ÷ 1000.0 → $2735.125/oz  ✓ (plausible)
```

### 2.3 Conflicting evidence — JForex API documentation

The JForex Java API exposes `Instrument.XAUUSD.getTickScale()`, which reportedly returns **2**.

In Dukascopy's JForex convention, a tick scale of `2` means prices have **2 decimal places**,
implying that the actual divisor is **10^2 = 100**.

Example JForex-API interpretation:
```
raw_integer 2735125 ÷ 100.0 → $27351.25/oz  ✗ (implausible at current prices)
raw_integer  273512 ÷ 100.0 → $2735.12/oz   ✓ (plausible — but different raw value assumed)
```

The discrepancy may indicate that the `getTickScale()` return value of `2` applies to price
**display precision** rather than directly to the raw integer divisor, or that the raw encoding
has a separate level of integer compression that the documentation does not make explicit.

### 2.4 Conflict summary

| Source                  | Implied scale | Decoded price (raw=2735125) | Plausible? |
|-------------------------|--------------|----------------------------|------------|
| Community parsers       | 1000.0        | \$2735.125/oz              | ✅ YES     |
| JForex `getTickScale()` | 100.0 (2 d.p.)| \$27351.25/oz              | ❌ NO      |
| JForex (alternative)    | 1000.0        | \$2735.125/oz              | ✅ (if getTickScale != divisor) |

---

## Section 3 — Evidence Inspected

### 3.1 Documentation sources reviewed

1. **Dukascopy JForex API Javadoc** — `Instrument.getTickScale()` return value semantics.
2. **Community JForex forums** — XAUUSD scale discussions; most references cite scale=1000.
3. **Open-source bi5 parsers** — multiple GitHub projects using scale=1000 for XAUUSD.
4. **GoldFlow instrument_spec.py** — current specification:
   ```python
   DUKASCOPY_XAUUSD_SPEC = ProviderInstrumentSpec(
       symbol="XAUUSD",
       price_scale=1000.0,
       volume_scale=1e6,
       pip_size=0.01,
       verification_status=VerificationStatus.UNVERIFIED_PENDING_CONFIRMATION,
       verification_notes=(
           "JForex API getTickScale()=2 conflicts with community scale=1000. "
           "Scale requires empirical verification against a known price reference."
       ),
   )
   ```

### 3.2 Synthetic fixture scale

The synthetic test fixtures in `tests/fixtures/synthetic_bi5.py` use
`SYNTHETIC_XAUUSD_FIXTURE_SPEC` with `price_scale=1000.0` and `allow_unverified_scale=True`.
This allows decoder unit tests to pass against synthetic data without constituting calibration
evidence against real market prices.

**The synthetic fixture scale does NOT confirm the real Dukascopy XAUUSD price scale.**

---

## Section 4 — Calibration Decision

### 4.1 Current status

**`DUKASCOPY_XAUUSD_SPEC.verification_status` = `UNVERIFIED_PENDING_CONFIRMATION`**

This status is set in `src/data/ingestion/instrument_spec.py` and enforced by
`execute_bounded_retrieval_pilot()` in `src/data/ingestion/dukascopy_provider.py`:

```python
if spec.verification_status == VerificationStatus.UNVERIFIED_PENDING_CONFIRMATION:
    raise UnverifiedPriceScaleError(
        f"Instrument {symbol} price scale is unverified. "
        "Real ingestion blocked until calibration evidence is produced."
    )
```

The fail-closed gate means that even if `allow_network=True` were set by an operator, XAUUSD
ingestion would still be blocked until the spec is promoted to `VERIFIED`.

### 4.2 What is needed to promote to VERIFIED

To mark `DUKASCOPY_XAUUSD_SPEC` as `VERIFIED`, the following evidence is required:

1. **Download one real `.bi5` file** for a specific UTC hour when XAUUSD market data is
   available (e.g., `XAUUSD/2024/09/01/08h_ticks.bi5` — October 2024, 08:00 UTC).
2. **Decode the first tick** using both candidate scales (1000.0 and 100.0).
3. **Compare decoded prices** against a reliable market reference at the same timestamp (e.g.,
   a broker's historical price, an exchange close, or a benchmark feed).
4. **Document the match**: instrument, UTC timestamp, raw integer, scale used, decoded price,
   reference price, deviation in pips.
5. **Write a calibration evidence record** and update `DUKASCOPY_XAUUSD_SPEC` to
   `VerificationStatus.VERIFIED`.

### 4.3 EURUSD calibration status (for reference)

`DUKASCOPY_EURUSD_SPEC` is currently marked `VERIFIED` with `price_scale=100000.0`.  This
reflects the widely-documented and community-confirmed five-decimal-place encoding for EURUSD.
The EURUSD pilot is eligible to proceed (subject to network authorisation); XAUUSD is not.

---

## Section 5 — Implications for Phase 6D and Phase 6E

| Item | Phase 6D | Phase 6E |
|------|----------|----------|
| XAUUSD real ingestion | ❌ BLOCKED | BLOCKED until scale verified |
| XAUUSD synthetic fixtures | ✅ ACTIVE | ✅ Continue |
| EURUSD real ingestion | 🔒 Network off by default | Eligible if operator enables |
| Decoder unit tests | ✅ 520 passed | — |

---

## Section 6 — Calibration Verification Requirements Summary

> **REQUIRES_PROVIDER_CONFIRMATION**  
> The XAUUSD price scale ambiguity must be resolved empirically before real XAUUSD tick data
> can be ingested.  Resolution requires a controlled single-file download during a future phase
> with explicit operator network authorisation.

**Unblocking checklist:**

- [ ] Operator authorises network access for calibration pilot (Phase 6E or later)
- [ ] Single `.bi5` file downloaded for a known UTC hour
- [ ] Both candidate scales (100.0, 1000.0) applied and compared to reference
- [ ] Match documented in a calibration evidence record
- [ ] `DUKASCOPY_XAUUSD_SPEC.verification_status` updated to `VERIFIED`
- [ ] `DUKASCOPY_XAUUSD_SPEC.price_scale` confirmed or corrected
- [ ] All 520+ existing tests still pass after spec update
- [ ] Calibration evidence appended to this report

---

*Report generated: 2026-10-29 | Phase: 6D | Repository: ad9807f*

