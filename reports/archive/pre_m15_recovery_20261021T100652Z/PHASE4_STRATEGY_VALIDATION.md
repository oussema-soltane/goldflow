# GoldFlow Phase 4 — SMC v1 Chronological Strategy Validation

**Generated UTC:** 2026-10-20T15:38:27.691061+00:00
**Strategy:** SMC v1 (frozen in `configs/smc_v1_frozen.json`)
**Data readiness:** READY_WITH_WARNINGS
**Execution spec:** MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE

> **IMPORTANT LIMITATIONS:**
> - Data provenance is **UNVERIFIED_PROVENANCE**: declared MT5, not independently authenticated.
> - The validate/holdout segments were visible during Phases 3C/3D full-history analysis. This is chronological stability testing, not genuinely unseen OOS validation.
> - Trade counts per segment are small. No statistical conclusions are supported.
> - Strategy parameters were NOT optimized on any segment.
> - Do not equate any positive backtest results with a repeatable live trading edge.

## Chronological Split Configuration

| Segment | Fraction |
|---|---|
| Training | 60% |
| Validation | 20% |
| Holdout | 20% |

The training segment overlaps with Phase 3C/3D inspection. The validation and holdout
segments provide chronological stability diagnostics only.

## H4 Results

**Data range:** 2023-07-26T21:00:00+00:00 to 2026-10-19T13:00:00+00:00
**Total rows:** 5000

| Segment | Rows | Start | End | Candidates | Rule Exits | EOD | Win Rate | Net P&L | Profit Factor | Max DD |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| train | 3000 | 2023-07-26 | 2025-07-04 | 7 | 6 | 0 | 33.33% | $566.48 | 2.48 | $751.76 |
| validate | 1000 | 2025-07-04 | 2026-02-25 | 4 | 0 | 0 | N/A | $0.00 | None | $0.00 |
| holdout | 1000 | 2026-02-26 | 2026-10-19 | 4 | 0 | 0 | N/A | $0.00 | None | $0.00 |

## H1 Results

**Data range:** 2025-12-05T04:00:00+00:00 to 2026-10-20T13:00:00+00:00
**Total rows:** 5000

| Segment | Rows | Start | End | Candidates | Rule Exits | EOD | Win Rate | Net P&L | Profit Factor | Max DD |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| train | 3000 | 2025-12-05 | 2026-06-15 | 14 | 11 | 0 | 45.45% | $768.25 | 2.54 | $356.30 |
| validate | 1000 | 2026-06-15 | 2026-08-18 | 2 | 0 | 0 | N/A | $0.00 | None | $0.00 |
| holdout | 1000 | 2026-08-18 | 2026-10-20 | 2 | 1 | 0 | 0.00% | $-97.52 | 0.00 | $146.24 |

## M15 Results

**Data range:** 2026-07-31T18:00:00+00:00 to 2026-10-20T15:15:00+00:00
**Total rows:** 5000

| Segment | Rows | Start | End | Candidates | Rule Exits | EOD | Win Rate | Net P&L | Profit Factor | Max DD |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| train | 3000 | 2026-07-31 | 2026-09-17 | 25 | 19 | 1 | 21.05% | $156.67 | 1.02 | $1,048.52 |
| validate | 1000 | 2026-09-17 | 2026-10-05 | 7 | 2 | 0 | 50.00% | $-58.99 | 0.28 | $128.94 |
| holdout | 1000 | 2026-10-05 | 2026-10-20 | 7 | 0 | 0 | N/A | $0.00 | None | $0.00 |

> **train END_OF_DATA warning:** $133.44 from forced liquidation at segment boundary. Excluded from win rate and profit factor but included in net P&L.

## M5 Results

**Data range:** 2026-09-22T23:15:00+00:00 to 2026-10-19T19:50:00+00:00
**Total rows:** 5000

| Segment | Rows | Start | End | Candidates | Rule Exits | EOD | Win Rate | Net P&L | Profit Factor | Max DD |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| train | 3000 | 2026-09-22 | 2026-10-08 | 20 | 13 | 1 | 15.38% | $-828.53 | 0.21 | $1,204.73 |
| validate | 1000 | 2026-10-08 | 2026-10-14 | 8 | 1 | 0 | 0.00% | $-94.92 | 0.00 | $122.92 |
| holdout | 1000 | 2026-10-14 | 2026-10-19 | 8 | 0 | 0 | N/A | $0.00 | None | $0.00 |

> **train END_OF_DATA warning:** $142.92 from forced liquidation at segment boundary. Excluded from win rate and profit factor but included in net P&L.

## Method Notes

- SMC detection runs on the full history up through each segment end to preserve swing/structure context.
- Only candidates whose signal bar falls within the target segment are evaluated.
- Signal bars, stop levels, and take-profit targets use the frozen SMC v1 rules (see `configs/smc_v1_frozen.json`).
- Trade execution: next-bar-open, bid-side bars, conservative stop-first, no look-ahead.
- END_OF_DATA exits excluded from win rate, profit factor, expectancy, and average R.
- Drawdown: close-to-close mark-to-market; OHLC cannot reveal intrabar minima.
- See `reports/smc_phase4_robustness_metrics.json` for cost sensitivity analysis.
