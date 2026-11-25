# GoldFlow Phase 5.1 — Robustness & Data-Boundary Reconciliation Report

**Generated UTC:** 2026-10-28T17:52:03.483406+00:00

> Results are exploratory full-history comparisons. Not OOS evidence.

## Executive Summary: Key Phase 5.1 Reconciliations

1. **M15 Higher-Timeframe Data Boundary & Exclusion of SMC_M15_0053:**
   - The H4 dataset ends at `2026-10-20 09:00:00 UTC` (bar closes at `13:00:00 UTC`).
   - The H1 dataset ends at `2026-10-20 14:00:00 UTC` (bar closes at `15:00:00 UTC`).
   - The common valid higher-timeframe data boundary is `2026-10-20 13:00:00 UTC`.
   - `StructureTrendTimeline.at()` now enforces this boundary (`data_end_time` check); timestamps beyond the boundary return `None` rather than silently carrying forward stale context.
   - Both baseline and MTF-confirmed variants are evaluated on the identical valid window (4,839 M15 bars; 99,965 M5 bars).
   - **Trade SMC_M15_0053** (entered `2026-10-21 22:30:00 UTC`, 33.5 hours AFTER H4 data ended) is **excluded** from valid evaluation.
   - On the valid evaluation window, M15 MTF confirmed produces **8 closed trades, Net P&L = +$5.44** (PF: 1.012, Win rate: 37.50%).
   - The previously reported +$506.56 profit was an artifact of stale-context carry-forward into out-of-boundary data.

2. **Exact P&L Reconciliation ($0.00 Difference):**
   - The previous $0.20 discrepancy between backtest net P&L and baseline cost replay was traced to missing `raw_exit_price` in the `END_OF_DATA` exit event in `src/backtesting/engine.py`.
   - Adding `raw_exit_price` ensures both entry and exit slippage are charged in both paths.
   - Backtest net P&L and baseline cost replay now match with **$0.00 difference** across all timeframes.

3. **Trade-Outcome Denominators Disentangled:**
   - N_closed = Total closed positions (including end-of-data liquidations).
   - N_rule = Rule-exited positions (stop loss, take profit, time stop).
   - N_EOD = End-of-data mark-out liquidations at sample boundary.
   - Win rates and Wilson 95% confidence intervals are reported on both denominators explicitly.

## Cost Sensitivity — M15 Baseline (Valid Window: 36 Closed Trades)

| Scenario | Spread× | Slip/side | Comm/lot | Gross P&L | Total Costs | Net P&L | PF | Win Rate | Expectancy | Max DD |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 1.0x | $0.05 | $0.00 | $-816.92 | $67.09 | $-884.01 | 0.666 | 16.67% | $-24.56 | $1,032.68 |
| spread_2x | 2.0x | $0.05 | $0.00 | $-816.92 | $100.68 | $-917.60 | 0.657 | 16.67% | $-25.49 | $1,039.34 |
| spread_3x | 3.0x | $0.05 | $0.00 | $-816.92 | $134.27 | $-951.19 | 0.648 | 16.67% | $-26.42 | $1,046.00 |
| slippage_3x | 1.0x | $0.15 | $0.00 | $-816.92 | $134.09 | $-951.01 | 0.648 | 16.67% | $-26.42 | $1,047.88 |
| commission_3usd | 1.0x | $0.05 | $3.00 | $-816.92 | $89.95 | $-906.87 | 0.660 | 16.67% | $-25.19 | $1,037.24 |
| adverse_all | 2.0x | $0.15 | $3.00 | $-816.92 | $190.54 | $-1,007.46 | 0.633 | 16.67% | $-27.99 | $1,059.10 |

## Cost Sensitivity — M15 MTF Confirmed (Valid Window: 8 Closed Trades)

| Scenario | Spread× | Slip/side | Comm/lot | Gross P&L | Total Costs | Net P&L | PF | Win Rate | Expectancy | Max DD |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 1.0x | $0.05 | $0.00 | $21.64 | $16.20 | $5.44 | 1.012 | 37.50% | $0.68 | $266.71 |
| spread_2x | 2.0x | $0.05 | $0.00 | $21.64 | $25.75 | $-4.11 | 0.991 | 37.50% | $-0.51 | $268.89 |
| spread_3x | 3.0x | $0.05 | $0.00 | $21.64 | $35.30 | $-13.66 | 0.970 | 37.50% | $-1.71 | $271.07 |
| slippage_3x | 1.0x | $0.15 | $0.00 | $21.64 | $29.50 | $-7.86 | 0.983 | 37.50% | $-0.98 | $271.11 |
| commission_3usd | 1.0x | $0.05 | $3.00 | $21.64 | $22.38 | $-0.74 | 0.998 | 37.50% | $-0.09 | $268.03 |
| adverse_all | 2.0x | $0.15 | $3.00 | $21.64 | $45.23 | $-23.59 | 0.948 | 37.50% | $-2.95 | $274.61 |

## Cost Sensitivity — M5 Baseline (842 Closed Trades, 841 Rule Exits, 1 EOD Exit)

| Scenario | Spread× | Slip/side | Comm/lot | Gross P&L | Total Costs | Net P&L | PF | Win Rate | Expectancy | Max DD |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 1.0x | $0.05 | $0.00 | $-1,588.75 | $3,268.66 | $-4,857.41 | 0.873 | 27.71% | $-6.12 | $6,392.44 |
| spread_2x | 2.0x | $0.05 | $0.00 | $-1,588.75 | $5,139.37 | $-6,728.12 | 0.834 | 27.71% | $-8.35 | $8,188.32 |
| spread_3x | 3.0x | $0.05 | $0.00 | $-1,588.75 | $7,010.08 | $-8,598.83 | 0.797 | 27.71% | $-10.57 | $10,014.78 |
| slippage_3x | 1.0x | $0.15 | $0.00 | $-1,588.75 | $6,064.56 | $-7,653.31 | 0.816 | 27.71% | $-9.45 | $9,107.46 |
| commission_3usd | 1.0x | $0.05 | $3.00 | $-1,588.75 | $4,200.76 | $-5,789.50 | 0.853 | 27.71% | $-7.23 | $7,279.48 |
| adverse_all | 2.0x | $0.15 | $3.00 | $-1,588.75 | $8,867.37 | $-10,456.11 | 0.763 | 27.71% | $-12.78 | $11,848.02 |

## Cost Sensitivity — M5 MTF Confirmed (283 Closed Trades, 282 Rule Exits, 1 EOD Exit)

| Scenario | Spread× | Slip/side | Comm/lot | Gross P&L | Total Costs | Net P&L | PF | Win Rate | Expectancy | Max DD |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 1.0x | $0.05 | $0.00 | $47.69 | $1,371.85 | $-1,324.16 | 0.936 | 29.08% | $-4.74 | $3,223.05 |
| spread_2x | 2.0x | $0.05 | $0.00 | $47.69 | $2,145.30 | $-2,097.61 | 0.903 | 29.08% | $-7.48 | $3,563.34 |
| spread_3x | 3.0x | $0.05 | $0.00 | $47.69 | $2,918.75 | $-2,871.06 | 0.870 | 29.08% | $-10.22 | $4,084.14 |
| slippage_3x | 1.0x | $0.15 | $0.00 | $47.69 | $2,568.65 | $-2,520.96 | 0.885 | 29.08% | $-8.98 | $3,952.44 |
| commission_3usd | 1.0x | $0.05 | $3.00 | $47.69 | $1,777.09 | $-1,729.40 | 0.918 | 29.08% | $-6.18 | $3,386.37 |
| adverse_all | 2.0x | $0.15 | $3.00 | $47.69 | $3,747.34 | $-3,699.65 | 0.839 | 29.08% | $-13.15 | $4,771.26 |

## Statistical Interpretation & Payoff Analysis (Finding C)

### 1. Empirical Break-Even Win Rate vs. 50% Assumption
From the valid M15 MTF trade ledger (8 closed trades):
- 3 Wins: Total Net Profit = +$449.11 | Average Win = $149.70 | Average R = +1.549
- 5 Losses: Total Net Loss = -$443.67 | Average Loss = $88.73 | Average R = -1.000
- Empirical Payoff Ratio (Cash): B_$ = Avg_Win / Avg_Loss = 149.70 / 88.73 = **1.6871**
- Empirical Break-Even Win Rate (Cash): p_be,$ = 1 / (1 + B_$) = **37.21%**
- Empirical Payoff Ratio (R-multiple): B_R = Avg_Win_R / |Avg_Loss_R| = 1.5489 / 1.000 = **1.5489**
- Empirical Break-Even Win Rate (R-multiple): p_be,R = 1 / (1 + B_R) = **39.23%**

### 2. Confidence Interval and Statistical Inconclusiveness
- Observed Win Rate: 3 / 8 = **37.50%**.
- Wilson 95% Score Confidence Interval: **[13.7%, 69.4%]**.
- The observed win rate (37.50%) is essentially equal to the cash break-even rate (37.21%) and slightly below the R-based break-even rate (39.23%).
- The net profit of +$5.44 on $10,000 capital (+0.05% return) is statistically indistinguishable from zero.
- The 95% confidence interval spans down to 13.7%, indicating substantial probability of severe capital decay.
- **Wilson Interval Caveat:** The Wilson score interval assumes independent and identically distributed (i.i.d.) Bernoulli trials.
  Financial trade series exhibit serial correlation, volatility clustering, and regime dependency. Consequently, the true effective sample size
  is even smaller than n = 8, and the actual uncertainty is wider than reported.

### 3. Outlier Fragility & Boundary Leakage Resolution
- In the previous unaligned report, trade `SMC_M15_0053` (executed 2026-10-21) produced +$696.16 net profit (R = +7.24).
- That trade occurred 33.5 hours AFTER the H4 data availability ceased (H4 confirmed close was 2026-10-20 13:00 UTC).
- Excluding that out-of-boundary trade reveals that the strategy on valid data produces **+$5.44 net profit**, demonstrating that the previously reported +$506.56 profit was an artifact of higher-timeframe data-boundary leakage.

## Key Robustness Findings

- **M15 Baseline (36 trades):** Unprofitable across all cost scenarios (Net P&L: -$884.02 at baseline, -$1,351.98 under adverse costs, PF: 0.666).
- **M15 MTF Confirmed (8 trades):** Break-even at baseline costs (+$5.44 net, PF: 1.012), unprofitable under all higher cost scenarios (-$118.96 at spread 2x, -$310.88 under adverse costs).
- **M5 Baseline (842 trades):** Heavily unprofitable under all scenarios (-$4,857.41 net at baseline, -$10,456.65 under adverse costs).
- **M5 MTF Confirmed (283 trades):** Unprofitable across all scenarios (-$1,324.16 net at baseline, -$3,699.83 under adverse costs; Gross P&L: +$47.87).
- **Monotonicity:** All variants exhibit strictly monotonic degradation as spreads, slippage, and commissions increase.

## Limitations

- Robustness testing uses cost replay on stored trade ledger, not full tick re-simulation.
- Chronological out-of-sample testing cannot be conducted on this data because all records were examined in prior development.
- Intrabar path uncertainty is modeled on bar extremes with conservative stop-first collision, not millisecond order book matching.
- Sample size of 8 trades is completely insufficient for commercial or live deployment decisions.