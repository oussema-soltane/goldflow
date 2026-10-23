# GoldFlow Phase 4 — SMC v1 Chronological Strategy Validation

**Generated UTC:** 2026-10-22T11:16:31.374491+00:00
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

## H1 Results

**Data range:** 2025-01-31T14:00:00+00:00 to 2026-10-20T14:00:00+00:00
**Total rows:** 10000

| Segment | Rows | Start | End | Candidates | Rule Exits | EOD | Win Rate | Net P&L | Profit Factor | Max DD |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| train | 6000 | 2025-01-31 | 2026-02-06 | 37 | 33 | 0 | 24.24% | $-251.54 | 0.89 | $1,249.98 |
| validate | 2000 | 2026-02-06 | 2026-06-15 | 12 | 9 | 0 | 55.56% | $926.75 | 3.73 | $356.30 |
| holdout | 2000 | 2026-06-15 | 2026-10-20 | 20 | 19 | 0 | 15.79% | $-982.92 | 0.29 | $1,233.92 |

## M15 Results

**Data range:** 2026-08-04T12:00:00+00:00 to 2026-10-22T09:15:00+00:00
**Total rows:** 5000

| Segment | Rows | Start | End | Candidates | Rule Exits | EOD | Win Rate | Net P&L | Profit Factor | Max DD |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| train | 3000 | 2026-08-04 | 2026-09-21 | 27 | 19 | 1 | 21.05% | $170.09 | 1.02 | $1,048.52 |
| validate | 1000 | 2026-09-21 | 2026-10-07 | 12 | 11 | 0 | 36.36% | $-78.24 | 0.88 | $1,364.54 |
| holdout | 1000 | 2026-10-07 | 2026-10-22 | 15 | 12 | 1 | 25.00% | $187.91 | 1.26 | $622.11 |

> **train END_OF_DATA warning:** $146.86 from forced liquidation at segment boundary. Excluded from win rate and profit factor but included in net P&L.

> **holdout END_OF_DATA warning:** $-25.16 from forced liquidation at segment boundary. Excluded from win rate and profit factor but included in net P&L.

## Method Notes

- SMC detection runs on the full history up through each segment end to preserve swing/structure context.
- Only candidates whose signal bar falls within the target segment are evaluated.
- Signal bars, stop levels, and take-profit targets use the frozen SMC v1 rules (see `configs/smc_v1_frozen.json`).
- Trade execution: next-bar-open, bid-side bars, conservative stop-first, no look-ahead.
- END_OF_DATA exits excluded from win rate, profit factor, expectancy, and average R.
- Drawdown: close-to-close mark-to-market; OHLC cannot reveal intrabar minima.
- See `reports/smc_phase4_robustness_metrics.json` for cost sensitivity analysis.
