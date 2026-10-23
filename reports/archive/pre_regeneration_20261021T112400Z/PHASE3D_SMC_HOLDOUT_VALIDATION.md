# GoldFlow Phase 3D — Frozen-Rule Chronological Holdout Validation

**Generated UTC:** 2026-10-20T14:39:15.641158+00:00
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
| H4 | 2025-10-29 | 2026-10-19 | 1500 | 5 | 0.04 / 0.08 | 1.0x | 4 | 4 | 0 | 0 | 1 | $133.39 | $0.00 | $133.39 | 50.00% | 1.68 | $142.32 | $100.00 |
| H4 | 2025-10-29 | 2026-10-19 | 1500 | 5 | 0.04 / 0.08 | 1.5x | 4 | 4 | 0 | 0 | 1 | $136.71 | $0.00 | $136.71 | 50.00% | 1.71 | $142.19 | $96.39 |
| H4 | 2025-10-29 | 2026-10-19 | 1500 | 5 | 0.04 / 0.08 | 2.0x | 4 | 4 | 0 | 0 | 1 | $135.03 | $0.00 | $135.03 | 50.00% | 1.69 | $142.06 | $97.66 |
| H1 | 2026-07-16 | 2026-10-20 | 1500 | 10 | 0.08 / 0.09 | 1.0x | 10 | 10 | 0 | 0 | 0 | $-591.95 | $0.00 | $-591.95 | 10.00% | 0.27 | $939.48 | $805.69 |
| H1 | 2026-07-16 | 2026-10-20 | 1500 | 10 | 0.08 / 0.09 | 1.5x | 10 | 10 | 0 | 0 | 0 | $-580.52 | $0.00 | $-580.52 | 10.00% | 0.27 | $905.38 | $794.15 |
| H1 | 2026-07-16 | 2026-10-20 | 1500 | 10 | 0.08 / 0.09 | 2.0x | 10 | 10 | 0 | 0 | 0 | $-582.67 | $0.00 | $-582.67 | 10.00% | 0.27 | $885.20 | $796.19 |
| M15 | 2026-09-25 | 2026-10-20 | 1500 | 19 | 0.10 / 0.17 | 1.0x | 1 | 0 | 0 | 1 | 18 | $0.00 | $1,785.29 | $1,785.29 | N/A | N/A | $1,838.85 | $0.00 |
| M15 | 2026-09-25 | 2026-10-20 | 1500 | 19 | 0.10 / 0.17 | 1.5x | 1 | 0 | 0 | 1 | 18 | $0.00 | $1,646.64 | $1,646.64 | N/A | N/A | $1,697.52 | $0.00 |
| M15 | 2026-09-25 | 2026-10-20 | 1500 | 19 | 0.10 / 0.17 | 2.0x | 1 | 0 | 0 | 1 | 18 | $0.00 | $1,645.32 | $1,645.32 | N/A | N/A | $1,697.64 | $0.00 |
| M5 | 2026-10-12 | 2026-10-19 | 1500 | 17 | 0.14 / 0.24 | 1.0x | 15 | 14 | 0 | 1 | 2 | $150.58 | $300.82 | $451.40 | 21.43% | 1.14 | $518.70 | $518.70 |
| M5 | 2026-10-12 | 2026-10-19 | 1500 | 17 | 0.14 / 0.24 | 1.5x | 15 | 14 | 0 | 1 | 2 | $116.29 | $299.59 | $415.88 | 21.43% | 1.11 | $533.66 | $533.66 |
| M5 | 2026-10-12 | 2026-10-19 | 1500 | 17 | 0.14 / 0.24 | 2.0x | 15 | 14 | 0 | 1 | 2 | $46.29 | $298.35 | $344.64 | 21.43% | 1.04 | $537.76 | $537.76 |

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
