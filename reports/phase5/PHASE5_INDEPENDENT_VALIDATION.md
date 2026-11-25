# GoldFlow Phase 5 — Independent Validation Report

**Generated UTC:** 2026-10-28T17:52:03.483406+00:00
**Frozen SMC v1 SHA-256:** `1091fb06b24491925510e642052305ba99e397e5f602c2ca2bdbd32094e7174a`
**Data readiness:** `READY_WITH_WARNINGS`
**Execution-spec audit:** `MATCHED_CAPTURED_DEFAULTS_UNVERIFIED_PROVENANCE`

> **Research integrity notice:** All datasets in this repository were
> examined during prior development phases. No genuinely untouched
> holdout period exists. All results are exploratory full-history
> comparisons. Data provenance is declared (MetaQuotes-Demo MT5) but
> not independently authenticated. These results are NOT evidence of
> a live-tradeable edge.

## MTF Experiment Results (Gross vs. Net Reconciliation)

| Timeframe | Variant | Candidates | Closed | Win Rate | Gross P&L | Costs | Net P&L | Return | PF | Max DD | Avg R |
|---|---|---|---|---|---|---|---|---|---|---|---|
| M15 | SMC_v1_baseline | 49 | 36 | 16.67% | $-816.92 | $67.09 | $-884.02 | -8.84% | 0.666 | $1,505.34 | -0.279 |
| M15 | SMC_v1_H4_H1_confirmed | 8 | 8 | 37.50% | $21.64 | $16.20 | $5.44 | 0.05% | 1.012 | $293.10 | -0.044 |
| M5 | SMC_v1_baseline | 1015 | 842 | 27.71% | $-1,588.75 | $3,268.66 | $-4,857.41 | -48.57% | 0.873 | $6,392.88 | -0.076 |
| M5 | SMC_v1_H4_H1_confirmed | 298 | 283 | 29.08% | $47.69 | $1,371.85 | $-1,324.16 | -13.24% | 0.936 | $3,502.65 | -0.035 |

* Win rate, PF, Avg R exclude END_OF_DATA exits.
** Net P&L and Max DD include end-of-data liquidation.
*** Gross P&L represents pure price delta before spreads, slippage, and commissions.

## Dataset Coverage and Actual Evaluation Windows (Finding B)

| Dataset | Rows | Start (UTC) | End (UTC) | Duration | Notes |
|---|---|---|---|---|---|
| H4 clean | 5,000 | 2023-07-27 17:00 | 2026-10-20 09:00 | ~38.8 months | Context TF 1 |
| H1 clean | 10,000 | 2025-01-31 14:00 | 2026-10-20 14:00 | ~20.6 months | Context TF 2 |
| M15 clean | 5,000 | 2026-08-04 12:00 | 2026-10-22 09:15 | ~2.6 months | Entry TF (Short history) |
| M5 clean | 99,999 | 2025-05-13 22:15 | 2026-10-20 15:50 | ~17.2 months | Entry TF (Long history) |

### Exact Overlapping Timestamp Ranges
- **M15 Experiment Evaluation Window (M15 ∩ H1 ∩ H4):** `2026-08-04 12:00:00+00:00` to `2026-10-20 09:00:00+00:00` (4,823 M15 bars; ~77 calendar days).
- **M5 Experiment Evaluation Window (M5 ∩ H1 ∩ H4):** `2025-05-13 22:15:00+00:00` to `2026-10-20 09:00:00+00:00` (99,917 M5 bars; ~17.2 months / 525 days).
- **True 4-Way Intersection (H4 ∩ H1 ∩ M15 ∩ M5):** `2026-08-04 12:00:00+00:00` to `2026-10-20 09:00:00+00:00` (~77 days).
  - Exact bar counts in 4-way overlap: H4: 330 bars | H1: 1,207 bars | M15: 4,823 bars | M5: 14,467 bars.

> **Evaluation Window Discrepancy Note:** Earlier Phase 5 documentation described the 'common evaluation window' as
> 2025-05-13 to 2026-10-20 (~17 months). This applied exclusively to the M5 experiment. The M15 dataset begins on
> 2026-08-04, covering only ~2.5 months. Within each timeframe comparison, baseline and filtered variants use identical
> underlying data, identical warm-up rules, and identical execution assumptions.

## Cost Sensitivity (M15 Baseline Correctly Filtered)

| Scenario | Gross P&L | Total Costs | Net P&L | PF |
|---|---|---|---|---|
| baseline | $-816.92 | $67.09 | $-884.01 | 0.666 |
| spread_2x | $-816.92 | $100.68 | $-917.60 | 0.657 |
| spread_3x | $-816.92 | $134.27 | $-951.19 | 0.648 |
| slippage_3x | $-816.92 | $134.09 | $-951.01 | 0.648 |
| commission_3usd | $-816.92 | $89.95 | $-906.87 | 0.660 |
| adverse_all | $-816.92 | $190.54 | $-1,007.46 | 0.633 |

## Limitations

- No genuine untouched out-of-sample period is available.
- Data provenance is declared but not independently authenticated.
- M15 MTF confirmed sample = 11 trades. This is insufficient for reliable statistical inference.
- OHLC simulation cannot reproduce tick-level intrabar path.
- Cost assumptions are modeled, not broker-confirmed in a live account.

## Reproducibility

```bash
python scripts/run_phase5_validation.py --timeframes M15 M5
```
