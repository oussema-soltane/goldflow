# GoldFlow — Phase 3B Research Data Readiness

**Generated (UTC):** 2026-10-20T15:57:58.547795+00:00
**Overall status:** READY_WITH_WARNINGS

This is a data eligibility audit for descriptive research only. It is not a strategy backtest or evidence of profitability.

## Timeframe Summary

| Timeframe | Status | Rows | Recommended minimum | Provenance | Date range |
|---|---:|---:|---:|---|---|
| H1 | REVIEW | 10000 | 5000 | real_source_declared | 2025-01-31 14:00:00+00:00 → 2026-10-20 14:00:00+00:00 |
| H4 | REVIEW | 5000 | 2000 | real_source_declared | 2023-07-27 17:00:00+00:00 → 2026-10-20 09:00:00+00:00 |
| M15 | REVIEW | 40000 | 5000 | real_source_declared | 2025-01-30 23:30:00+00:00 → 2026-10-20 15:30:00+00:00 |
| M5 | REVIEW | 99999 | 5000 | real_source_declared | 2025-05-13 22:15:00+00:00 → 2026-10-20 15:50:00+00:00 |

## Blockers

- None

## Dataset Warnings

### H1
- 17 intraday gap(s) detected (potential data outage).

### H4
- 11 intraday gap(s) detected (potential data outage).

### M15
- 29 intraday gap(s) detected (potential data outage).

### M5
- 51 intraday gap(s) detected (potential data outage).

## Next Step

If blocked, open MT5, log in to the demo account, verify the broker's exact Gold symbol, run `scripts/download_data.py` with real MT5 data, then rerun this audit. Do not present synthetic or unknown-provenance data as real-market findings.
