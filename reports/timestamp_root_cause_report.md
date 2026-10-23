> **Historical audit notice (2026-10-19):** This report describes the pre-reingestion dataset and is not the current readiness state. See `reports/research_readiness.md`; current data is `READY_WITH_WARNINGS`, with MT5 source provenance not independently authenticated.

# GoldFlow Phase 3B — Independent Review & Remediation

**Review date:** 2026-10-14  
**Decision:** BLOCKED — do not use the bundled datasets for session analysis, ICT event statistics, or backtesting.

## What was wrong with the previous changes?

1. **A fixed `-3 hour` correction was hard-coded into the loader.** The uploaded historical datasets span multiple seasons/years. If the feed uses EET/EEST rules, the offset changes seasonally; subtracting three hours from every historical bar shifts winter data incorrectly.
2. **The previous report treated an observed three-hour tick discrepancy as proof of a universal timestamp rule.** The discrepancy is useful evidence, but it conflicts with MetaTrader's official Python documentation, which says bar/tick timestamps returned by the API are UTC. The correct engineering response is a feed-specific diagnostic and explicit conversion mode—not a silent global offset.
3. **The previous regression tests encoded the assumed answer.** The tests created `corrected_dfs` by subtracting three hours from data that had already been shifted, so they could pass without proving the loader's conversion was correct. Several checks asserted source metadata strings rather than independently establishing provenance.
4. **The old reports and README were inconsistent.** Some described identical OHLC sequences while the newer audit said none were identical. Row-wise OHLC comparisons are only a basic duplication screen; they do not prove correct timeframe aggregation.
5. **The current raw CSV files do not preserve the original MT5 epoch integers.** Their timestamp strings already reflect the fixed offset. A matching SHA-256 only proves a file has not changed since the hash was written; it does not establish authenticity or correct timestamps.

## Changes made in this review

- Removed the hard-coded three-hour correction from the loader.
- Added two explicit timestamp modes:
  - `posix_utc` — default; follows the documented MT5 API timestamp convention and applies no offset.
  - `server_wall_clock` — optional compatibility mode for a feed empirically shown to encode server-local wall-clock values as epoch-like seconds.
- Added DST-aware conversion using an explicit IANA timezone in `server_wall_clock` mode. Ambiguous/nonexistent wall-clock times raise an error rather than being guessed.
- Added raw timestamp audit fields (`time_raw_epoch` and per-row correction seconds) to new raw downloads. These fields are dropped from the standardized processed dataset but retained in the raw CSV.
- Added sidecar fields for timestamp mode, source verification status, server timezone, correction range, and whether original epoch values were preserved.
- Fixed naive date input handling so `copy_rates_range` receives timezone-aware UTC datetimes; naive user inputs are explicitly interpreted as UTC.
- Updated research readiness so missing/legacy timestamp-conversion metadata and future candles relative to retrieval time block research.
- Replaced the hard-coded `-3h` timestamp tests with independent tests for POSIX mode, winter/summer timezone conversion, DST ambiguity, sidecar propagation, and legacy-data quarantine.
- Updated the README with the correct safe workflow and explicit mode selection.

## Current data disposition

The four bundled timeframes are now marked in their sidecars as:

- `timestamp_mode = legacy_fixed_offset_unverified`
- `timestamp_integrity_status = blocked_legacy_fixed_offset`
- `raw_timestamp_epoch_preserved = false`
- `source_verification_status = declared_not_independently_verified`

The CSV contents were not rewritten during this review. These files must be treated as quarantined historical artifacts, not as validated research data.

## What has not been verified

I did not have access to the user's live Windows MT5 terminal during this review. I therefore did not re-download market data or independently verify the live server's timestamp behavior. The `MetaTrader 5 API` source label in a sidecar remains a declaration until confirmed by a real retrieval run.

## Recommended next steps

1. Open MT5 and verify Windows time synchronization.
2. Run a fresh, read-only live tick/bar diagnostic during active trading and compare the returned epoch values with the machine's UTC clock.
3. If raw values behave as POSIX UTC, use the default `posix_utc` mode.
4. If the feed is demonstrably encoded as server-local wall-clock values, confirm its IANA timezone/DST rules and use `server_wall_clock` with that timezone.
5. Re-download all four timeframes into a clean working copy, preserving raw epoch values.
6. Run the timestamp audit, readiness audit, and full test suite. Investigate every failure rather than declaring failures "expected."
7. Keep strategy backtesting blocked until the new files pass the readiness gate.

## External reference

MetaTrader's official Python API documentation states that bar data returned by the terminal uses UTC timestamps. This is why the loader defaults to `posix_utc` and requires explicit evidence before applying a server-local conversion:
- https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py
- https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesrange_py


## Additional integration fixes in the reviewed package

- Added `scripts/diagnose_mt5_timestamps.py`, a read-only live tick/bar diagnostic. It compares the POSIX candidate and, when supplied, a timezone-aware server-wall-clock candidate against the machine UTC clock. It never places orders and returns `INCONCLUSIVE` when neither candidate is close enough.
- Added a confirmation gate. A dataset remains blocked until the operator explicitly confirms that the live diagnostic was reviewed and the selected timestamp mode was chosen.
- Updated the Streamlit Market Analysis page to expose the timestamp mode, pass the selected mode into ingestion, propagate metadata into sidecars, and warn when timestamps are unverified or data is synthetic.
- Fixed a separate provenance bug in the Streamlit page: it previously called `save_processed_data()` without `source_metadata=meta`, which would discard source/retrieval/timestamp metadata from newly saved sidecars.
- Added `tzdata` to dependencies so IANA timezone rules are available on Windows installations.
- The Backtesting page remains a Phase 4 placeholder; no strategy backtest was run or approved.

## Final validation in this review

- `compileall` for `src`, `scripts`, `pages`, and `app.py`: **passed**.
- `python -m pytest tests -q`: **146 passed, 0 failed**.
- `scripts/research_readiness.py`: **BLOCKED**, as intended for the quarantined legacy data.
- Live MT5 retrieval from this review environment: **not performed**.
