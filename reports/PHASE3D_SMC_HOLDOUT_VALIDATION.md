# GoldFlow Phase 3D — Frozen-Rule Chronological Holdout Validation

**Generated UTC:** 2026-10-22T10:08:07.849970+00:00
**Readiness:** READY_WITH_WARNINGS
**Execution specification audit:** MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE

> **Critical limitation:** this is a chronological holdout inside historical data already inspected during Phase 3C/3D. It is useful for checking temporal stability and cost sensitivity, but it is not an untouched independent confirmation of profitability.

## Protocol

- The first 70% of each timeframe's bars supply structure/swing context; signals are eligible only in the final 30%.
- SMC setup rules and thresholds are frozen; no parameters were optimized on the holdout.
- Same holdout candidates are evaluated at 1.0x, 1.5x and 2.0x transaction costs. Observed spread points, fallback spread, slippage and commission scale together.
- Metrics separate rule exits (including optional TIME_STOP exits) from END_OF_DATA liquidation; all end-of-data trades remain marked explicitly. This frozen-rule cost-only validator defaults to no time stop.
- Each timeframe has its own date split; results are **not directly comparable across timeframes** because their history ranges differ.

## Holdout windows and results

| TF | Holdout start UTC | Holdout end UTC | Bars | Candidates | Spread median / p90 ($/oz) | Cost | Closed | Rule exits | Time stops | EOD exits | Skipped | Rule-exit P&L | End-data P&L | Net P&L | Win % | PF | Max DD (MTM) | Realized DD |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| H4 | 2025-10-30 | 2026-10-20 | 1500 | 5 | 0.04 / 0.08 | 1.0x | 4 | 4 | 0 | 0 | 1 | $133.39 | $0.00 | $133.39 | 50.00% | 1.68 | $142.32 | $100.00 |
| H4 | 2025-10-30 | 2026-10-20 | 1500 | 5 | 0.04 / 0.08 | 1.5x | 4 | 4 | 0 | 0 | 1 | $136.71 | $0.00 | $136.71 | 50.00% | 1.71 | $142.19 | $96.39 |
| H4 | 2025-10-30 | 2026-10-20 | 1500 | 5 | 0.04 / 0.08 | 2.0x | 4 | 4 | 0 | 0 | 1 | $135.03 | $0.00 | $135.03 | 50.00% | 1.69 | $142.06 | $97.66 |
| H1 | 2026-04-13 | 2026-10-20 | 3000 | 28 | 0.07 / 0.08 | 1.0x | 25 | 25 | 0 | 0 | 3 | $-499.13 | $0.00 | $-499.13 | 24.00% | 0.70 | $1,257.89 | $1,006.89 |
| H1 | 2026-04-13 | 2026-10-20 | 3000 | 28 | 0.07 / 0.08 | 1.5x | 25 | 25 | 0 | 0 | 3 | $-504.97 | $0.00 | $-504.97 | 24.00% | 0.70 | $1,261.43 | $1,011.96 |
| H1 | 2026-04-13 | 2026-10-20 | 3000 | 28 | 0.07 / 0.08 | 2.0x | 25 | 25 | 0 | 0 | 3 | $-498.83 | $0.00 | $-498.83 | 24.00% | 0.70 | $1,252.99 | $1,005.04 |
| M15 | 2026-09-29 | 2026-10-22 | 1500 | 23 | 0.10 / 0.17 | 1.0x | 20 | 19 | 0 | 1 | 3 | $-151.58 | $-25.16 | $-176.74 | 21.05% | 0.89 | $1,632.95 | $906.61 |
| M15 | 2026-09-29 | 2026-10-22 | 1500 | 23 | 0.10 / 0.17 | 1.5x | 20 | 19 | 0 | 1 | 3 | $-200.90 | $-25.52 | $-226.42 | 21.05% | 0.85 | $1,643.32 | $918.10 |
| M15 | 2026-09-29 | 2026-10-22 | 1500 | 23 | 0.10 / 0.17 | 2.0x | 20 | 19 | 0 | 1 | 3 | $-203.03 | $-25.88 | $-228.91 | 21.05% | 0.85 | $1,643.12 | $919.03 |
| M5 | 2026-05-13 | 2026-10-20 | 30000 | 317 | 0.08 / 0.18 | 1.0x | 272 | 271 | 0 | 1 | 45 | $-3,134.85 | $258.80 | $-2,876.05 | 28.04% | 0.80 | $4,255.59 | $4,142.82 |
| M5 | 2026-05-13 | 2026-10-20 | 30000 | 317 | 0.08 / 0.18 | 1.5x | 272 | 271 | 0 | 1 | 45 | $-3,399.85 | $257.60 | $-3,142.25 | 28.04% | 0.78 | $4,349.47 | $4,232.66 |
| M5 | 2026-05-13 | 2026-10-20 | 30000 | 317 | 0.08 / 0.18 | 2.0x | 271 | 270 | 0 | 1 | 46 | $-3,548.27 | $256.40 | $-3,291.87 | 27.78% | 0.76 | $4,506.89 | $4,389.35 |

## How to interpret this report

- **Rule-exit P&L** is the sum of completed non-END_OF_DATA trades, net of modeled costs. It excludes positions forcibly marked at the final bar.
- **Net P&L** includes END_OF_DATA liquidation. Do not interpret that figure without reading the separate end-data P&L column.
- A small trade count is not enough evidence to infer a stable edge. Compare trade count, profit factor, expectancy, drawdown, and cost sensitivity together.
- Max DD (MTM) uses close-to-close estimated liquidation values for open positions; realized DD ignores floating P&L and is included only as a diagnostic. Neither reconstructs worst intrabar equity from OHLC bars.
- If results turn negative under 1.5x or 2.0x costs, the strategy is fragile to execution uncertainty under these assumptions.
- Spread percentiles are based on the bar `spread` field converted using configured `point_size`; zero values use fallback spread at execution time. The source declares MT5 API provenance, but the broker contract/point specifications are not independently verified.
- OHLC bars cannot reveal true intrabar event order; the engine applies stop-first when stop and target are both hit. This remains a model assumption, not tick-level reconstruction.
- This report is not a walk-forward optimization, live-forward test, or genuine untouched out-of-sample validation.

## Artifacts

- `smc_oos_validation_metrics.json` — full machine-readable validation results.
- `smc_oos_validation_trades.csv` — every closed/skipped trade for each cost scenario.
