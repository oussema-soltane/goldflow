# GoldFlow Phase 3E — Multi-Timeframe SMC Experiment

**Generated UTC:** 2026-10-28T17:51:54.696764+00:00
**Entry timeframes:** M15, M5
**Context:** H4 + H1 latest completed structure direction
**Frozen SMC v1 SHA-256:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`
**Data readiness:** `READY_WITH_WARNINGS`
**Execution-spec audit:** `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE`

> This is an exploratory research comparison, not a live-trading claim or genuine untouched out-of-sample validation. Source provenance remains declared, not independently authenticated.

## Comparison results

| Timeframe | Variant | Candidates | Closed | Rule exits | Win rate* | Net P&L** | Return | Profit factor* | Max DD (MTM) | Avg R* |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| M15 | SMC_v1_baseline | 49 | 36 | 36 | 16.67% | $-884.02 | -8.84% | 0.67 | $1,505.34 | -0.28 |
| M15 | SMC_v1_H4_H1_confirmed | 8 | 8 | 8 | 37.50% | $5.44 | 0.05% | 1.01 | $293.10 | -0.04 |
| M5 | SMC_v1_baseline | 1015 | 842 | 841 | 27.71% | $-4,857.41 | -48.57% | 0.87 | $6,392.88 | -0.08 |
| M5 | SMC_v1_H4_H1_confirmed | 298 | 283 | 282 | 29.08% | $-1,324.16 | -13.24% | 0.94 | $3,502.65 | -0.04 |

* Win rate, profit factor and average R exclude `END_OF_DATA` mark-outs as defined by the shared event-driven engine.
** Net P&L includes end-of-data liquidation. Max DD is close-to-close mark-to-market and is not an intrabar maximum.

## Filtering funnel

### M15
- Original candidates: 49
- Accepted after H4/H1 alignment: 8
- Rejected: 41
- candidate_direction_mismatch: 15
- higher_timeframe_conflict: 26

### M5
- Original candidates: 1015
- Accepted after H4/H1 alignment: 298
- Rejected: 717
- candidate_direction_mismatch: 320
- higher_timeframe_conflict: 397

## Causal timing contract

A structure-break event on H4/H1 is available only at its candle close, computed as the event candle's open timestamp plus the source timeframe duration. For a lower-timeframe candidate, context is sampled at its `next_bar_time` (the intended entry open). Events whose availability is later than that entry timestamp are excluded. A missing H4/H1 context, disagreement between H4 and H1, or mismatch with the candidate direction rejects the experimental entry.

## Limitations

- This is an exploratory full-history comparison. The bundled records have already been examined during earlier phases; this is not an untouched out-of-sample result.
- Sidecars declare MT5 provenance but the broker/source history is not independently authenticated.
- Candidate count and observed win rate can fall sharply after higher-timeframe filtering; small samples do not support strong statistical conclusions.
- The context filter uses the latest structure-break state known at entry, not a full discretionary market-structure interpretation.
- OHLC event simulation cannot reconstruct tick-level intrabar path or guarantee future live execution.

## Artifacts

- `smc_mtf_metrics.json` — compact machine-readable comparison and metrics.
- `smc_mtf_trades.csv` — both variants' trade ledgers, keyed by stable baseline setup ID.
- `smc_mtf_equity_curves.csv` — mark-to-market and realized equity curves, stored separately from JSON.
- `smc_mtf_candidate_context_audit.csv` — per-candidate H4/H1 direction and availability audit.
- `smc_mtf_powerbi_summary.csv` — flat comparison table suitable for Power BI Desktop import.
